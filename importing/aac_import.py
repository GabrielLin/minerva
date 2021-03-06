# AAC corpus importer
#
# Copyright:   (c) Daniel Duma 2015
# Author: Daniel Duma <danielduma@gmail.com>

# For license information, see LICENSE.TXT

from __future__ import print_function
from __future__ import absolute_import
import os, re

from importing.corpus_import import CorpusImporter
import db.corpora as cp
from db.base_corpus import BaseReferenceMatcher
from scidoc.xmlformats.read_paperxml import PaperXMLReader
from importing.aan_metadata import convertAANcitations
from proc.nlp_functions import tokenizeText, basic_stopwords
from string import punctuation
from proc.general_utils import getRootDir


class AANReferenceMatcher(BaseReferenceMatcher):
    """
        Matches references using information from the annotated AAN corpus
    """

    def __init__(self, infile):
        """
            Loads AAN citation graph

            Args:
                infile: path to acl.txt
        """
        super(self.__class__, self).__init__(cp.Corpus)
        self.citations = convertAANcitations(infile)
        # keep track of which document we're processing so that we only load
        # the references once
        self.current_corpus_id = None

    def processBOW(self, text):
        """
            Takes a list of strings, returns a set of tokens.
        """
        text = " ".join(text)
        text = text.lower()
        text = re.sub(r"[\.,;\-\"]", " ", text)
        tokens = tokenizeText(text)
        ##        tokens=text.lower().split()
        tokens = [token for token in tokens if token not in punctuation and token not in basic_stopwords]
        return set(tokens)

    def makeBOW(self, metadata):
        """
            Returns a simple bag-of-words of a reference/citation
        """
        text = []
        if metadata.get("raw_string", "") != "":
            text.append(metadata["raw_string"])
        else:
            text.append(metadata.get("title", ""))
            text.append(metadata.get("year", ""))
            if "authors" in metadata:
                authors = metadata["authors"]
            else:
                authors = metadata["metadata"]["authors"]

            for author in metadata["authors"]:
                text.append(author.get("given", ""))
                text.append(author.get("family", ""))

            text.append(metadata.get("journal", ""))
            text.append(metadata.get("booktitle", ""))
            text.append(metadata.get("publisher", ""))
            text.append(metadata.get("location", ""))
            text.append(metadata.get("pages", ""))
        return self.processBOW(text)

    def authorsBOW(self, metadata):
        """
        """
        text = []
        for author in metadata["authors"]:
            text.append(author.get("given", ""))
            text.append(author.get("family", ""))
        return self.processBOW(text)

    def autorsYearMatch(self, cit_data, ref):
        """
            True if year in the BOW and at least 1 token overlaps in authos and BOW
        """
        return (cit_data["data"]["year"] in ref["bow"]) and (len(cit_data["authors_bow"] & ref["bow"]) > 0)

    def chooseNextBest(self, cit_data):
        """
            Very simple choosing function, using set intersection
        """
        scores = []
        for ref in self.available_references:
            if not self.autorsYearMatch(cit_data, ref):
                continue
            score = len(ref["bow"] & cit_data["bow"])
            if score > len(cit_data["bow"]) / 4:
                scores.append([score, ref])

        res = sorted(scores, key=lambda x: x[0], reverse=True)
        if len(res) > 0:
            return res[0][1]
        else:
            return None

    def loadReferenceData(self, doc):
        """
            Loads all data for AAN annotated citation links from Corpus,
            matches references in the document with them
        """
        self.current_corpus_id = doc.metadata["corpus_id"]
        # load data
        if doc.metadata["corpus_id"] not in self.citations:
            print("Can't find outlinks for file ", doc.metadata["corpus_id"])
            return None

        print("Matching outlinks with references for ", doc.metadata["corpus_id"])
        self.guid_index = {}
        self.doc_outlinks = []

        for cited_id in self.citations[doc.metadata["corpus_id"]]:
            metadata = cp.Corpus.getMetadataByField("metadata.corpus_id", cited_id)
            if metadata:
                ##                metadata=metadata["metadata"]
                self.doc_outlinks.append({
                    "bow": self.makeBOW(metadata),
                    "data": metadata,
                    "authors_bow": self.authorsBOW(metadata),
                })

        self.available_references = []
        for ref in doc.references:
            self.available_references.append({"bow": self.makeBOW(ref), "data": ref})

        # match each AAN-sponsored paper with its best reference in the doc
        for cit_data in self.doc_outlinks:
            chosen_ref = self.chooseNextBest(cit_data)
            if chosen_ref:
                ##                print(json.dumps(chosen_ref["data"]),"\n",json.dumps(cit_data["data"]),"\n\n")
                chosen_ref["data"]["guid"] = cit_data["data"]["guid"]
                chosen_ref["data"]["corpus_id"] = cit_data["data"].get("corpus_id", "")
                self.guid_index[chosen_ref["data"]["guid"]] = cit_data["data"]
                self.available_references.remove(chosen_ref)
            else:
                print("Couldn't match reference ", cit_data["data"]["corpus_id"])

    def matchReference(self, ref, doc):
        """
            Gateway function for matching reference with metadata.

            In practice, it loads and matches data the first time it's called
            for a new SciDoc.
        """
        cp.Corpus.checkConnectedToDB()

        if doc.metadata["corpus_id"] != self.current_corpus_id:
            self.loadReferenceData(doc)

        # every reference should have been pre-matched. Return guid if available, else None
        if ref.get("guid", "") != "":
            return self.guid_index[ref["guid"]]
        else:
            return None


def getACL_corpus_id(filename):
    """
        Returns the ACL id for a file
    """
    return os.path.split(filename)[1].replace("-paper.xml", "").lower()


def import_aac_corpus(endpoint, use_celery=True):
    """
        Do the importing of the AAC corpus
    """
    importer = CorpusImporter(reader=PaperXMLReader())
    importer.collection_id = "AAC"
    importer.import_id = "initial"
    importer.generate_corpus_id = getACL_corpus_id

    options = {
        # "list_missing_references":True, # default: False
        # "convert_and_import_docs": False,  # default: True
    }

    ##    corpus_import.FILES_TO_PROCESS_FROM=10222
    ##    corpus_import.FILES_TO_PROCESS_TO=500

    ##    importer.restartCollectionImport(options)
    cp.Corpus.matcher = AANReferenceMatcher(os.path.join(getRootDir("aan"), "release" + os.sep + "acl_full.txt"))

    importer.use_celery = use_celery
    importer.importCorpus(os.path.join(getRootDir("aac"), "inputXML"), file_mask="*-paper.xml", import_options=options)


##    from corpus_import import updatePaperInCollectionReferences
# G:\NLP\PhD\aac\inputXML\anthology\W\W11-2139-paper.xml
##    updatePaperInCollectionReferences("faa45dc5-44f1-4990-921c-674e616f8a94", options)


def fix_citation_parent_aac():
    """
    """
    from proc.results_logging import ProgressIndicator
    cp.useElasticCorpus()
    cp.Corpus.connectCorpus(getRootDir("aac"))

    guids = cp.Corpus.listPapers({"match": {"metadata.collection_id": "AAC"}})
    progress = ProgressIndicator(True, len(guids), True)
    for guid in guids:
        doc = cp.Corpus.loadSciDoc(guid)
        for cit in doc.citations:
            if "parent" in cit:
                cit["parent_s"] = cit.pop("parent")
        cp.Corpus.saveSciDoc(doc)
        progress.showProgressReport("Fixing badly imported PaperXML")


def main():
    from multi.celery_app import set_config

    endpoint = set_config("aws-server")

    cp.useElasticCorpus()
    cp.Corpus.connectCorpus(getRootDir("aac"), endpoint=endpoint)
    cp.Corpus.createAndInitializeDatabase()

    # import_aac_corpus(endpoint, use_celery=False)

    # fix_citation_parent_aac()

    ##    import corpora as cp
    ##    cp.useElasticCorpus()
    ##    cp.Corpus.connectCorpus("g:\\nlp\\phd\\aac")
    ##    print(cp.Corpus.listPapers("year:>2010")[:100])

    pass


if __name__ == '__main__':
    main()
