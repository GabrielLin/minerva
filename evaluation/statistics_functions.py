# <purpose>
#
# Copyright:   (c) Daniel Duma 2016
# Author: Daniel Duma <danielduma@gmail.com>

# For license information, see LICENSE.TXT

import sys

from minerva.proc.nlp_functions import CORESC_LIST, AZ_ZONES_LIST
import minerva.db.corpora as cp


def getAnnotationStatistics(doc):
    """
        Given a scidoc, computes

        :param doc: scidoc
        :type doc: scidoc
    """
    csc_counts={x:0 for x in CORESC_LIST}
    az_counts={x:0 for x in AZ_ZONES_LIST}
    zone_list=[]

    for sentence in doc.allsentences:
        if sentence.get("csc_type","") != "":
            csc_counts[sentence["csc_type"]] += 1
            zone_list.append(sentence["csc_type"])

    return {
            "csc_type_counts":csc_counts,
            "az_counts":az_counts,
            "zone_list":zone_list,
            "num_sentences":len(doc.allsentences),
            "num_sections":len(doc.allsections),
            }

def computeAnnotationStatistics(guid):
    """
        Store for each scidoc statistics on the PMC annotation

        :param guid: the uuid of the paper to compute statistics for
    """
    try:
        doc=cp.Corpus.loadSciDoc(guid)
        stats=getAnnotationStatistics(doc)
        cp.Corpus.setStatistics(guid, stats)
    except:
        print("Error computing statistics for %s :", sys.exc_info()[:2])

def main():
    cp.useElasticCorpus()
    from minerva.squad.config import MINERVA_ELASTICSEARCH_ENDPOINT
    cp.Corpus.connectCorpus("",endpoint=MINERVA_ELASTICSEARCH_ENDPOINT)
##    doc=cp.Corpus.loadSciDoc("957e1fcf-d5b4-41dc-af32-7db08f1d2ded")
##    print getAnnotationStatistics(doc)
##    computeAnnotationStatistics("957e1fcf-d5b4-41dc-af32-7db08f1d2ded")
##    print cp.Corpus.getStatistics("957e1fcf-d5b4-41dc-af32-7db08f1d2ded")
    pass

if __name__ == '__main__':
    main()