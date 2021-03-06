# JSON-serializable data structure and helper functions to work with the contents
# of a scientific paper.
#
# Copyright:   (c) Daniel Duma 2014
# Author: Daniel Duma <danielduma@gmail.com>

# For license information, see LICENSE.TXT

from __future__ import print_function

from __future__ import absolute_import
import json, sys, re
from copy import deepcopy

from proc.nlp_functions import rx_word_boundaries, replaceXMLCitationsWithUnderscoreCitations, AUTHOR_MARKER, \
    CIT_MARKER, cleanXML
from scidoc.citation_utils import CITATION_FORM
from scidoc.reference_formatting import formatAPACitationAuthors, formatReference
import six

SENTENCE_TYPES = ["s", "fig-caption", "s-li"]
PARAGRAPH_TYPES = ["p", "footnote", "p-li"]
SECTION_TYPES = ["section"]


class SciDoc(object):
    """
        Class for storing a "scientific document" in memory and working with its
        contents.

        Makes it easy to retrieve sentence, paragraphs, citations and references
        individually.

        It is immediately serializable to JSON, with no circular references in
        the memory structure. Every element in the document (citation, sentence,
        paragraph, reference, [*to expand*]) has a unique id, and can be retrieved
        with .element_by_id[].

        There are specialized functions for building the document in memory,
        matching citations with references, serializing to JSON, and pretty
        printing the document as either text or HTML.

        TODO:
            - How to deal with
                - sections inside bibliography?
                - sections inside abstract?
                - bullet point lists & ordered lists: sentences, paragraphs?

    """

    def __init__(self, data=None, ignore_errors=None):
        """
            :param data: either a string (file name) or a dict from which to load the
                         scidoc
            :param ignore_errors: a list of errors to ignore.

        """
        # the actual contents, as serialized to JSON
        self.data = {
            "content": [],  # all inline elements
            "references": [],  # papers cited by this paper: references at the end of the document
            "citations": [],  # citations to these references inside the paper
            "inline_elements": [],
            "metadata": {"filename": "",
                         "guid": "",
                         "corpus_id": "",
                         "doi": "",
                         "authors": [],
                         "surnames": [],
                         "year": "",
                         "title": ""}}

        # global variables to keep track of importing/exporting
        self.glob = {}
        self.ignore_errors = ignore_errors if ignore_errors else []
        self.known_author_strings = None

        if data:
            if isinstance(data, six.string_types):
                self.loadFromFile(data)
            elif isinstance(data, dict) and "content" in data and "references" in data and "metadata" in data:
                self.data = data

        self.updateContentLists()

    def __repr__(self):
        return self.data.__repr__()

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, item):
        self.data[key] = item

    def loadExistingMetadata(self, metadata):
        """
        """
        self.data["metadata"] = metadata
        self.updateContentLists()

    def processSingleElement(self, element):
        """
            Updates the dicts for a single item, typically to be used just after
            an item has been added
        """
        if self.isSentence(element):
            self.allsentences.append(element)
        if self.isParagraph(element):
            self.allparagraphs.append(element)
        if self.isSection(element):
            self.allsections.append(element)
        self.element_by_id[element["id"]] = element

    def updateContentLists(self):
        """
            Processes the contents of self.data and updates the lists and dicts
        """
        # lists of all sentences, etlc. for fast access to contents by
        # index or for iteration
        self.allsentences = []
        self.allparagraphs = []
        self.allsections = []
        self.element_by_id = {}
        self.abstract = {}
        self.citation_by_id = {}
        self.reference_by_id = {}
        self.ignore_errors = ["error_match_citation_with_reference"]

        for element in self.data["content"]:
            self.processSingleElement(element)

        # try to find abstract section
        for section in self.allsections:
            if section["header"].lower() == "abstract":
                self.abstract = section

        # if unsuccessful, set the first section to be the abstract
        if len(self.allsections) > 0:
            self.abstract = self.allsections[0]

        self.updateReferences()

    @property
    def metadata(self):
        return self.data["metadata"]

    @property
    def references(self):
        return self.data["references"]

    @property
    def citations(self):
        return self.data["citations"]

    @property
    def content(self):
        return self.data["content"]

    def updateReferences(self):
        """
            Updates the dictionary of quick access to references with the data
            and updates the ["citations"] links for each reference
        """
        self.reference_by_id = {}
        self.citation_by_id = {}

        for ref in self.data["references"]:
            if self.isReference(ref):
                self.reference_by_id[ref["id"]] = ref

        for cit in self.data["citations"]:
            self.citation_by_id[cit["id"]] = cit
            # update citations link for the reference
            if cit["ref_id"]:
                try:
                    ref_citations = self.reference_by_id[cit["ref_id"]]["citations"]
                    if cit["id"] not in ref_citations:
                        ref_citations.append(cit["id"])
                except KeyError as e:
                    if "error_match_citation_with_reference" in self.ignore_errors:
                        # print("Cannot match citation %s with reference %s, ignoring." % (cit["id"], cit["ref_id"]))
                        continue
                    else:
                        raise KeyError("Cannot match citation with reference")

    def isSentence(self, element):
        """
            True if element is sentence. This includes figure captions, list items, footnotes
        """
        return element["type"] in SENTENCE_TYPES

    def isParagraph(self, element):
        """
            True if element is paragraph
        """
        return element["type"] in PARAGRAPH_TYPES

    def isSection(self, element):
        """
        """
        return element["type"] in SECTION_TYPES

    def isReference(self, element):
        """
        """
        return element["type"] == "reference"

    def isCitation(self, element):
        """
        """
        return element["type"] == "cit"

    def getElementIndex(self, element):
        """
        """
        if self.isSentence(element):
            return self.allsentences.index(element)
        elif self.isParagraph(element):
            return self.allparagraphs.index(element)
        elif self.isSection(element):
            return self.allsections.index(element)
        else:
            return None

    def addElement(self, element):
        """
            Handy for adding an element without worrying about IDs and updating dicts
        """
        if self.isSentence(element):
            element["id"] = "s" + str(len(self.allsentences))
        if self.isParagraph(element):
            element["id"] = "p" + str(len(self.allparagraphs))
        if self.isSection(element):
            element["id"] = "sect" + str(len(self.allsections))

        self.data["content"].append(element)
        # add element to parent's list of content
        if element["parent"] != "root":
            self.element_by_id[element["parent"]]["content"].append(element["id"])

        self.processSingleElement(element)
        return element

    def addSection(self, parent, header, header_id=None):
        """
            Create a new section element, add to SciDoc, set header_id if provided

            :param parent: id of section it hangs from, or set parent to None or "root" if it is a root section
            :param header: heading text of section
        """
        if parent is None:
            parent = "root"
        newElement = {"type": "section", "header": header, "content": [], "parent": parent}
        if header_id:
            newElement["header_id"] = header_id
        return self.addElement(newElement)

    def addParagraph(self, parent):
        """
            Create a new paragraph element, add to SciDoc

            :param parent: id of element (section) it hangs from
        """
        newElement = {"type": "p", "content": [], "parent": parent}
        return self.addElement(newElement)

    def addSentence(self, parent, text=""):
        """
            Create a new sentence element, add to SciDoc
        """
        newElement = {"type": "s", "text": text, "parent": parent}
        return self.addElement(newElement)

    def addCitation(self, sent_id=None, ref_id=None):
        """
            Create a new citation element, automatically set id, return it
            for further filling of fields
        """
        newCitation = {
            "id": "cit" + str(len(self.data["citations"])),
            "parent_s": sent_id,
            "ref_id": ref_id,
        }
        self.data["citations"].append(newCitation)
        self.citation_by_id[newCitation["id"]] = newCitation
        return newCitation

    def addReference(self):
        """
            Create a new reference element, automatically set id, return it
            for further filling of fields
        """
        newReference = {
            "type": "reference",
            "id": "ref" + str(len(self.data["references"])),
            "authors": [],
            "surnames": [],
            "citations": []}
        self.data["references"].append(newReference)
        self.reference_by_id[newReference["id"]] = newReference
        return newReference

    def addExistingReference(self, existing_reference):
        """
            Add an existing reference to the document's references, giving
            it an id and filling in essential fields. This is meant to be used
            with output from an external citation parsing service like ParsCit
            or FreeCite.
        """
        newReference = deepcopy(existing_reference)
        newReference["id"] = "ref" + str(len(self.data["references"]))
        newReference["type"] = "reference"
        newReference["citations"] = []
        self.data["references"].append(newReference)
        self.reference_by_id[newReference["id"]] = newReference
        return newReference

    def matchReferenceById(self, ref_id):
        """
            Matches and returns a reference by its unique id
        """
        for ref in self.data["references"]:
            if ref["id"] == ref_id:
                return ref
        return None

    def matchReferenceByCitationId(self, cit_id):
        """
            Matches and returns the reference that a citation id refers to
        """
        match = self.citation_by_id.get(cit_id, None)
        if match:
            return self.matchReferenceById(match["ref_id"])
        return None

    def findMatchingReferenceByOriginalId(self, id):
        """
            Returns a reference from the bibliography by its original_id if found, None otherwise
        """
        for ref in self["references"]:
            if ref.get("original_id", None) == str(id):
                return ref
        return None

    def loadFromData(self, data):
        """
            Runs the functions to update the *_by_id dicts and other shortcuts
        """
        self.data = data
        self.updateContentLists()
        self.updateReferences()

    def loadFromFile(self, filename):
        """
            Loads the json into [data] and calls loadFromData
        """
        try:
            f = open(filename, "rb")
            res = json.load(f)
            f.close()
        except:
            print("Exception in SciDoc.loadFromFile():", sys.exc_info()[:2])
            return None

        self.loadFromData(res)

    def getJSONstring(self):
        """
            Returns a json string representation of self
        """
        return json.dumps(self.data)

    def saveToFile(self, filename, indent=2):
        """
            A wrapper that json.dump's() self.data to a file and catches the
            potential exception
        """
        try:
            f = open(filename, "wb")
            json.dump(self.data, f, indent=indent)
            f.close()
        except:
            print("Exception in SciDoc.saveToFile(): %s" % sys.exc_info()[:2])

    def addWordCountToSentences(self):
        """
            Iterate over sentences, add word count to each sentence dict
        """

        def num_words_in_line(line):
            return len(rx_word_boundaries.findall(line)) >> 1

        for s in self.allsentences:
            s["wordlen"] = num_words_in_line(s["text"])

    def getParagraphText(self, p):
        """
            Returns the plain text representation of a paragraph
        """
        res = ""
        for s in p["content"]:
            sent = self.element_by_id[s]
            if isinstance(sent, dict) and "text" in sent:
                res += sent["text"] + " "
        return res

    def getSectionText(self, section, headers=False):
        """
            Returns the text contained in a section, headers optional
        """
        text = ""
        if headers:
            text += section.get("header", "") + "\n"

        for element_id in section.get("content", []):
            element = self.element_by_id[element_id]
            if self.isSection(element):
                text += self.getSectionText(element, headers)
            elif self.isParagraph(element):
                text += self.getParagraphText(element) + "\n"

        return text

    def getAbstract(self):
        text = self.getSectionText(self.abstract)
        text = cleanXML(text)
        return text

    def getFullDocumentText(self, headers=False, include_bibliography=False, cit_style="APA", exclude_abstract=False):
        """
            Returns the whole document in plain text. Basic function for
            indexing purposes. For fancier rendering, see render_content.py

            Args:
                headers: boolean. Add headers to the text?
                include_bibiliography: boolean. Print the bibliography too?
                cit_style: what style of citations to use
            Returns:
                a string with the rendered document
        """

        def recurseSectionsBibliography(biblos):
            res = ""

            if isinstance(biblos, dict) and "references" in biblos:
                # here we should be adding the different bibliography sections, but in a plain TXT file it makes little sense
                ##            if biblos.has_key("header"):
                ##                  res += biblos ["header"]
                for ref in biblos["references"]:
                    if ref["type"] == "subsection":
                        res += recurseSectionsBibliography(ref)
                    elif ref["type"] == "ref":
                        if ref.get("text", "") != "":  # if the reference is in raw text, not processed
                            reftext = ref["text"]
                        else:
                            reftext = formatReference(ref)
                        res += reftext + "\n\n"
            return res

        def processElement(element):
            result = ""
            if self.isSection(element):
                if headers:
                    result += element["header"] + " \n"
            if self.isSentence(element):
                result += element["text"] + " "
            return result

        text = self.data["metadata"]["title"] if self.data["metadata"]["title"] is not None else ""
        text += "\n\n"

        to_ignore = []
        if exclude_abstract and self.abstract:
            to_ignore.append(self.abstract["id"])
            for element_id in self.abstract["content"]:
                to_ignore.append(element_id)
                element = self.element_by_id[element_id]
                if element["type"] == "p":
                    for s_id in element["content"]:
                        to_ignore.append(s_id)

        to_ignore = set(to_ignore)

        for element in self.data["content"]:
            if exclude_abstract and element["id"] in to_ignore:
                continue
            text += processElement(element)

        biblio_add = ""
        if include_bibliography and "references" in self.data:
            biblio_add += recurseSectionsBibliography(self.data["references"])

            if len(biblio_add) > 0:
                text += "\n\nBibliography\n\n"
                text += biblio_add

        return text

    def formatTextForExtraction(self, text):
        """
        Returns the text with the citation placeholders substituted by a single token
         __cit and every author reference replaced with __author.

        This prepares the text for query extraction, context extraction and KW Selection

        :return: text ready for extraction
        """

        if not self.known_author_strings:
            self.prepareGazetteer()

        # text = re.sub(r"<CIT.+?/>", CIT_MARKER, text)
        text = replaceXMLCitationsWithUnderscoreCitations(text)
        text = cleanXML(text)

        for author_regex in self.known_author_strings:
            try:
                text = re.sub(author_regex + "(\s*\,?\s*\d+\w?)?", AUTHOR_MARKER + " ", text)
                text = re.sub(author_regex + "(\s*\(\d+\w?\))?", AUTHOR_MARKER + " ", text)
            except Exception as e:
                print(e)

        text = re.sub("\(\s*\_\_author\s*\.\)?", "( " + AUTHOR_MARKER + " )", text)
        text = re.sub("(\w)" + re.escape(CIT_MARKER), r"\1 " + CIT_MARKER, text)
        text = re.sub(re.escape(AUTHOR_MARKER) + "\s*\(\d+\w?\)", AUTHOR_MARKER + " ", text)
        # text = re.sub(re.escape(CIT_MARKER+CIT_MARKER), CIT_MARKER+" "+CIT_MARKER, text)
        return text

    def prepareGazetteer(self):
        """
        Populates the gazetteer of author names to replace with __author
        """
        inline_ref_mentions = []
        for ref in self.references:
            # inline_ref_mentions.extend(ref["surnames"])
            # print(formatAPACitationAuthors(ref))
            text = formatAPACitationAuthors(ref)
            if text.strip() == "?":
                continue

            names = []
            if " and " in text:
                names = [name.strip().replace("\\ ", "\\s*") for name in text.split("and")]
                names = [r"\b%s\b" % name for name in names]

            text = re.escape(text)
            text = text.replace("al\.", "al\.?\,?")
            text = text.replace(r"\ and\ ", "\ (and|\&amp\;|\&)\ ")
            text = text.replace("\\ ", "\\s*")
            # print(text)
            inline_ref_mentions.append(text)
            # names_from_institution=ref["institution"].replace()
            inline_ref_mentions.extend(names)

        inline_ref_mentions = set([ref for ref in inline_ref_mentions if re.search("[A-Z]", ref)])
        self.known_author_strings = list(inline_ref_mentions)

    def countMultiCitations(self, newSent):
        """
            Locate and cluster together multiple citations in a single sentence,
            i.e. (Johns & Smith (2005), Bla and Bla (2007))
        """
        cits = []
        ed = newSent["text"]

        match = 1

        while match:
            match = re.search(r"(<cit\sid=(.{1,6})\s?/>).{0,7}<cit\sid=(.{1,6})\s?/>", ed, re.IGNORECASE)
            if match:
                c1 = match.group(2).strip()
                c2 = match.group(3).strip()
                cits.append([c1, c2])
                ed = ed[:match.start(1)] + ed[match.end(1):]

        groups = []

        for cit in cits:
            added = False

            for group in groups:
                if cit[0] in group:
                    group.append(cit[1])
                    added = True
                    break
            if not added:
                groups.append(cit)

        for group in groups:
            for cit_id in group:
                if cit_id in self.citation_by_id:
                    cit = self.citation_by_id[cit_id]
                    cit["multi"] = len(group)
                    cit["group"] = group

    def updateAuthorsAffiliations(self):
        """
            It adds the doc's guid to the authors' list of publications per
            affiliation. It has to be done in this awkward way or it won't
            be possible to know which affiliation goes with which paper.
        """
        for author in self.metadata["authors"]:
            for aff in author.get("affiliation", []):
                if self.metadata["guid"] != "":
                    aff["papers"] = [self.metadata["guid"]]
                else:
                    aff["papers"] = []

    def extractSentenceTextWithCitationTokens(self, s, sent_id):
        """
            Returns a printable representation of the sentence where all
            references are now placeholders with numbers.
        """
        global ref_rep_count
        ref_rep_count = 0

        newSent = self.element_by_id[sent_id]

        def repFunc(match):
            """
                This is called by the re.sub() function for every citation match.
            """
            global ref_rep_count
            ref_rep_count += 1

            ref_id = match.group(1).replace("\"", "").replace("'", "")
            if ref_id in self.reference_by_id:
                res = CITATION_FORM % six.text_type(self.citation_by_id[newSent["citations"][ref_rep_count - 1]]["id"])
            else:
                res = match.group(0).replace(u"xref", u"inref")
                print("Ran out of citations for sentence: this is bad")
                print(match.group(0))
                print(newSent)
            return res

        text = s.renderContents(encoding=None)
        newSent["text"] = text
        text = re.sub(r"<xref.*?rid=\"(.*?)\".*?>(.*?)</xref>", repFunc, text, 0, re.IGNORECASE | re.DOTALL)
        return text


def basicTest():
    newSent = json.loads("""
     {
      "text": "Bilingual alignment methods  <CIT ID=cit21 /> <CIT ID=cit22 /> <CIT ID=cit23 /> <CIT ID=cit24 /> <CIT ID=cit25 /> <CIT ID=cit26 /> <CIT ID=cit27 /> <CIT ID=cit28 /> <CIT ID=cit29 /> <CIT ID=cit30 /> <CIT ID=cit31 />. have been used in statistical machine translation  <CIT ID=cit32 />, terminology research and translation aids  <CIT ID=cit33 /> <CIT ID=cit34 /> <CIT ID=cit35 />, bilingual lexicography  <CIT ID=cit36 /> <CIT ID=cit37 />, word-sense disambiguation  <CIT ID=cit38 /> <CIT ID=cit39 /> and information retrieval in a multilingual environment  <CIT ID=cit40 />.",
      "citations": [
        "cit21",
        "cit22",
        "cit23",
        "cit24",
        "cit25",
        "cit26",
        "cit27",
        "cit28",
        "cit29",
        "cit30",
        "cit31",
        "cit32",
        "cit33",
        "cit34",
        "cit35",
        "cit36",
        "cit37",
        "cit38",
        "cit39",
        "cit40"
      ],
      "type": "s",
      "id": "s155",
      "parent": "p36"
    }
    """)
    doc = SciDoc("g:\\nlp\\phd\\bob\\filedb\\jsondocs\\a94-1006.json")
    doc.countMultiCitations(newSent)


def main():
    pass


if __name__ == '__main__':
    main()
