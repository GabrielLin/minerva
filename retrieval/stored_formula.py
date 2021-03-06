# <purpose>
#
# Copyright:   (c) Daniel Duma 2015
# Author: Daniel Duma <danielduma@gmail.com>

# For license information, see LICENSE.TXT

from __future__ import absolute_import
import re
from collections import defaultdict
import six
from functools import reduce

TERM_POSITION_IN_TUPLE = 6


class StoredFormula:
    """
        Stores a Lucene explanation and makes it easy to set weights on the
        formula post-hoc and recompute
    """

    def __init__(self, formula=None):
        if formula:
            self.formula = formula
        else:
            self.formula = {}
        self.round_to_decimal_places = 4

    def __getitem__(self, key):
        return self.formula[key]

    def __setitem__(self, key, item):
        self.formula[key] = item

    def truncate(self, f, n):
        '''Truncates/pads a float f to n decimal places without rounding'''
        s = '{}'.format(f)
        if 'e' in s or 'E' in s:
            return '{0:.{1}f}'.format(f, n)
        i, p, d = s.partition('.')
        return '.'.join([i, (d + '0' * n)[:n]])

    def fromLuceneExplanation(self, explanation):
        """
            Loads the formula from a Lucene explanation.

            WARNING: deprecated. This function may not work well, update it to
            do what .fromElasticExplanation does
        """
        original_value = explanation.getValue()

        if not explanation.isMatch():
            self.formula = {"coord": 0, "matches": []}
            return

        details = explanation.getDetails()
        self.formula["matches"] = []

        if "weight(" in details[0].getDescription():  # if coord == 1 it is not reported
            matches = details
            self.formula["coord"] = 1
        else:
            matches = details[0].getDetails()
            self.formula["coord"] = details[1].getValue()

        for match in matches:
            desc = match.getDescription()
            field = re.match(r"weight\((.*?)\:", desc, re.IGNORECASE)
            # using dicts
            ##            newMatch={"field":field.group(1)}
            ##            elem=match.getDetails()[0]
            ##            if "fieldWeight" in elem.getDescription():
            ##                # if the queryWeight is 1, .explain() will not report it
            ##                newMatch["qw"]=1.0
            ##                newMatch["fw"]=elem.getValue()
            ##            else:
            ##                elements=elem.getDetails()
            ##                newMatch["qw"]=elements[0].getValue()
            ##                newMatch["fw"]=elements[1].getValue()
            # using namedtuple
            ##            newMatch=namedtuple("retrieval_result",["field","qw","fw"])
            ##            newMatch.field=str(field.group(1))
            ##            elem=match.getDetails()[0]
            ##            if "fieldWeight" in elem.getDescription():
            ##                # if the queryWeight is 1, .explain() will not report it
            ##                newMatch.qw=1.0
            ##                newMatch.fw=elem.getValue()
            ##            else:
            ##                elements=elem.getDetails()
            ##                newMatch.qw=elements[0].getValue()
            ##                newMatch.fw=elements[1].getValue()

            # using tuple
            field_name = str(field.group(1))
            elem = match.getDetails()[0]
            if "fieldWeight" in elem.getDescription():
                # if the queryWeight is 1, .explain() will not report it
                newMatch = (field_name, 1.0, elem.getValue())
            else:
                elements = elem.getDetails()
                newMatch = (field_name, elements[0].getValue(), elements[1].getValue())
            self.formula["matches"].append(newMatch)

        # just checking

    ##        original_value=self.truncate(original_value,self.round_to_decimal_places)
    ##        computed_value=self.truncate(self.computeScore(defaultdict(lambda:1),self.round_to_decimal_places))
    ##        assert(computed_value == original_value)

    def fromElasticExplanation(self, explanation, save_terms=False):
        """
            Loads the formula from a Lucene explanation
        """

        def iterateDetail(detail):
            """
                Recursive function that processes a detail


            """
            if detail["description"].startswith("coord"):
                new_element = {"type": "coord", "value": detail["value"]}
            elif detail["description"].startswith("sum of"):
                new_element = {"type": "+", "parts": []}
                for new_detail in detail["details"]:
                    new_element["parts"].append(iterateDetail(new_detail))
            elif detail["description"].startswith("product of"):
                new_element = {"type": "*", "parts": []}
                for new_detail in detail["details"]:
                    new_element["parts"].append(iterateDetail(new_detail))
            elif detail["description"].startswith("max of"):
                new_element = {"type": "max", "parts": []}
                for new_detail in detail["details"]:
                    new_element["parts"].append(iterateDetail(new_detail))
            else:
                # score=(field,qw,fw,tf,docFreq,maxDocs,term)
                qw = None
                fw = None
                tf = None
                docFreq = None
                maxDocs = None

                field = re.match(r"weight\((.*?)\:(.*?)\sin", detail["description"], re.IGNORECASE)
                if field:
                    field_name = str(field.group(1))
                    term = six.text_type(field.group(2))
                    elem = detail["details"][0]
                    if elem["description"].startswith("fieldWeight"):
                        qw = 1.0
                        fw = float(elem["value"])
                        # if the queryWeight is 1, .explain() will not report it
                        ##                        new_element={"type":"hit", "field":field_name, "qw": 1.0, "fw":elem["value"]}
                        # (field_name,query_weight,field_weight,term)
                        if save_terms:
                            new_element = (field_name, qw, fw, term)
                        else:
                            new_element = (field_name, qw, fw)
                    else:
                        elements = elem["details"]

                        qw = elements[0]["value"]
                        fw = elements[1]["value"]

                        for element in elements:
                            if docFreq and tf:
                                break
                            for detail in element["details"]:
                                idf_match = re.match(r"idf\(docFreq=(\d+),\smaxDocs=(\d+).*?\)", detail["description"],
                                                     re.IGNORECASE)
                                if idf_match:
                                    docFreq = int(idf_match.group(1))
                                    maxDocs = int(idf_match.group(2))
                                    break

                            for detail in element["details"]:
                                tf_match = re.match(r"tf\(freq=(.+?)\).*", detail["description"],
                                                     re.IGNORECASE)
                                if tf_match:
                                    tf = int(float(tf_match.group(1)))
                                    break

                        if save_terms:
                            new_element = (field_name, qw, fw, tf, docFreq, maxDocs, term)
                        else:
                            new_element = (field_name, qw, fw, tf, docFreq, maxDocs)
                ##                        new_element={"type":"hit", "field":field_name, "qw": elements[0]["value"], "fw":elements[1]["value"]}
                elif detail["description"].startswith("match on required clause, product of"):
                    new_element = {"type": "const", "value": detail["value"]}

            return new_element

        original_value = explanation["explanation"]["value"]

        if not explanation["matched"]:
            self.formula = {"coord": 0, "matches": []}
            return

        self.formula = iterateDetail(explanation["explanation"])

        # While not done checking that this works, this assert is in place

    ##        original_value=self.truncate(original_value,self.round_to_decimal_places)
    ##        computed_value=self.truncate(self.computeScore(self.formula,defaultdict(lambda:1)),self.round_to_decimal_places)
    ##        assert(computed_value == original_value)

    def computeScore(self, part=None, field_parameters=None, kw_parameters=None):
        """
            Recomputation of a Lucene explain formula using the values in
            @field_parameters as per-field query weights and @kw_parameters as
            per-keyword query weights.

            Recursive. Call with None or
            formula.formula as parameter first, it will iterate from there.

            :param part: tuple, list or dict
            :returns: floating-point score
        """
        if part is None:
            part = self.formula

        if isinstance(part, tuple) or isinstance(part, list):
            if field_parameters:
                field_multiplier = field_parameters[part[0]]
            else:
                field_multiplier = 1

            if kw_parameters:
                if len(part) <= 3:
                    raise ValueError("Record missing 4th parameter: <term>")
                query_weight = kw_parameters.get(part[TERM_POSITION_IN_TUPLE], 0) * part[1]
                # part[TERM_POSITION_IN_TUPLE] should be the actual term string.
                # NOTE: only matching exact terms. If kw not in dict, score of 0
            else:
                query_weight = part[1]  # qw

            return query_weight * field_multiplier * part[2]  # qw * param * fw (tf * idf * fieldNorm)

        elif isinstance(part, dict):
            if part["type"] in ["*", "+", "max"]:
                scores = [self.computeScore(sub_part, field_parameters, kw_parameters) for sub_part in part["parts"]]
                if part["type"] == "*":
                    return reduce(lambda x, y: x * y, scores)
                elif part["type"] == "+":
                    return sum(scores)
                elif part["type"] == "max":
                    return max(scores)
            elif part["type"] in ["const", "coord"]:
                assert (part["value"] is not None)
                return part["value"]
            ##        elif part["type"] == "hit":
            ##            return part["qw"] * field_parameters[part["field"]] * part["fw"]
            else:
                raise ValueError("Unexpected operation type: %s" % part["type"])
        else:
            raise ValueError("Unexpected type %s" % type(part))


def main():
    pass


if __name__ == '__main__':
    main()
