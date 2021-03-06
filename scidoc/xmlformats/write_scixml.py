# SciXML writer class
#
# Copyright:   (c) Daniel Duma 2015
# Author: Daniel Duma <danielduma@gmail.com>

# For license information, see LICENSE.TXT

from __future__ import absolute_import
from __future__ import print_function
import re, codecs

from proc.general_utils import safe_unicode
from .base_classes import BaseSciDocXMLReader,BaseSciDocXMLWriter
import six

def escapeText(text):
    """
        Escapes (X/H)TML characters in the string
    """
    text=re.sub(r"(>|&gt;)","&gt;",text, flags=re.IGNORECASE)
    text=re.sub(r"(<|&lt;)","&lt;",text, flags=re.IGNORECASE)
    text=re.sub(r"(&|&amp;)","&amp;",text, flags=re.IGNORECASE)
    return text

class SciXMLWriter(BaseSciDocXMLWriter):
    """

    """
    def __init__(self):
        """
        """
        self.header_depth=0
        self.already_rendered=[]

    def writeMetadata(self, doc):
        """
        """
        lines=[]
        lines.append("<METADATA>")
        if "fileno" in doc["metadata"]:
            lines.append("<FILENO>"+escapeText(doc.metadata["fileno"])+"</FILENO>\n")

        lines.append("<TITLE>"+escapeText(doc.metadata["title"])+"</TITLE>\n")
        lines.append("<FILENAME>"+escapeText(doc.metadata["filename"])+"</FILENAME>\n")

        lines.append("<APPEARED>")
        if "conference" in doc.metadata:
            lines.append("<CONFERENCE>"+(doc.metadata["conference"])+"</CONFERENCE>\n")
        if "journal" in doc.metadata:
            lines.append("<JOURNAL>"+(doc.metadata["journal"])+"</JOURNAL>\n")

##        lines.append(u"<CURRENT_AUTHORLIST>")
##        for author in doc.metadata["authors"]:
##            lines.append(u"<CURRENT_AUTHOR>")
##            lines.append("<FIRSTNAME>%s</FIRSTNAME>" % author["given"])
##            lines.append(u"<CURRENT_SURNAME>%s</CURRENT_SURNAME>" % author["family"])
##            lines.append(u"</CURRENT_AUTHOR>")
##        lines.append(u"</CURRENT_AUTHORLIST>")

        lines.append(u"<AUTHORS>")
        for author in doc.metadata["authors"]:
            lines.append("<AUTHOR>%s %s</AUTHOR>" % (escapeText(author["given"]),escapeText(author["family"])))
        lines.append(u"</AUTHORS>")


##        lines.append("<SURNAMES>")
##        for author in doc["authors"]:
##
##        lines.append("</SURNAMES>")

        lines.append(u"<YEAR>"+doc.metadata["year"]+"</YEAR>")
        lines.append(u"</APPEARED>")

        if "revisionhistory" in doc["metadata"]:
            lines.append(u"<REVISIONHISTORY>"+escapeText(doc.metadata["revisionhistory"])+u"</REVISIONHISTORY>\n")
        lines.append(u"</METADATA>")
        return lines

    def writeAbstract(self, doc):
        """
        """
        lines=[]
        lines.append(u"<ABSTRACT>")
        if "content" in doc.abstract:
            for element_id in doc.abstract["content"]:
                s=doc.element_by_id[element_id]
                if s["type"]=="s":
                    lines.append(self.writeSentence(doc,s, True))
                if s["type"]=="p":
                    lines.extend(self.writeParagraph(doc,s, True))
        lines.append(u"</ABSTRACT>")
        return lines

    def processSentenceText(self, s, doc):
        """
            Allows overriding by descendant classes to do some processing of
            the sentence text when saving, e.g. POS-tagging every word
        """
        return escapeText(s["text"])

    def writeSentence(self, doc, s, in_abstract=False):
        """
            Fixes all the contents of the sentence, returns a string of proper XML
        """

        def repl_func(m):
            """
                Replaces <CIT ID=0 /> with <REF ID=cit0 REFID=ref0 />
            """
            cit_id=m.group(1) # this is the actual unique identifier of a citation in the document
            ref_id=doc.citation_by_id[cit_id]["ref_id"] # this is the id of the reference the cit cites
            return u'<REF ID="'+safe_unicode(cit_id)+u'" REFID="'+safe_unicode(ref_id)+'" />'

        if in_abstract:
            xmltag=u"A-S"
        else:
            xmltag=u"S"

        res=u"<"+xmltag+u' ID="A-%s"' % s["id"]

        if "az" in s:
            res+=u' AZ="%s"' % s["az"]

        text=self.processSentenceText(s, doc)
        text=re.sub(r"<CIT ID=(.*?)\s?/>",repl_func, text)
        res+=">"+text+"</"+xmltag+">"

        return res

    def writeParagraph(self, doc,paragraph, in_abstract=False):
        """
        """
        lines=[]

        # fix for empty paragraphs: should it be here?
        if len(paragraph["content"]) == 0:
            return lines

        if not in_abstract:
            lines.append(u"<P>")
        for element in paragraph["content"]:
            element=doc.element_by_id[element]
            if element["type"]=="s":
                lines.append(self.writeSentence(doc,element, in_abstract))

        if not in_abstract:
            lines.append(u"</P>")
        return lines

    def writeSection(self, doc,section, header_depth):
        """
        """
        if section["id"] in self.already_rendered:
            return []
        self.already_rendered.append(section["id"])

        self.header_depth+=1
        lines=[]
        lines.append(u'<DIV DEPTH="'+str(header_depth+1)+'">')
        lines.append(u"<HEADER ID='H-1'>%s</HEADER>" % (escapeText(section["header"])))
        for element in section["content"]:
            element=doc.element_by_id[element]
            if element["type"]=="section":
                lines.extend(self.writeSection(doc,element, header_depth))
            elif element["type"]=="p":
                lines.extend(self.writeParagraph(doc,element))

        lines.append(u"</DIV>")
        self.header_depth-=1
        return lines

    def writeBody(self, doc):
        """
        """
        lines=[]
        lines.append(u"<BODY>")
        for section in doc.allsections:
            if section != doc.abstract:
                lines.extend(self.writeSection(doc,section,0))
        lines.append(u"</BODY>")
        return lines

    def writeRefAuthor(self, doc,author):
        """
        """
        lines=[]
        lines.append(u"<AUTHOR>")
        if isinstance(author,six.string_types):
            lines.append(escapeText(author))
        elif isinstance(author,dict):
            lines.append(escapeText(author.get("given","")))
            lines.append(u"<SURNAME>%s</SURNAME>" % escapeText(author.get("family","")))
        lines.append(u"</AUTHOR>")
        return lines

    def writeRefAuthors(self, doc, ref):
        """
        """
        lines=[]
        lines.append("<AUTHORLIST>")
        for author in ref["authors"]:
            lines.extend(self.writeRefAuthor(doc,author))
        lines.append("</AUTHORLIST>")
        return lines

    def writeReference(self, doc, ref):
        """
        <REFERENCE ID="cit1">
        <AUTHORLIST>
        <AUTHOR>L.<SURNAME>Que, Jr.</SURNAME></AUTHOR>
        <AUTHOR>R. Y. N.<SURNAME>Ho</SURNAME></AUTHOR>
        </AUTHORLIST>
        <TITLE></TITLE>
        <JOURNAL>Chem. Rev.<YEAR>1996</YEAR>962607-2624</JOURNAL></REFERENCE>
        """
        lines=[]
        lines.append('<REFERENCE ID="%s">' % ref["id"])
        lines.extend(self.writeRefAuthors(doc,ref))
        lines.append("<TITLE>%s</TITLE>" % escapeText(ref["title"]))
        lines.append("<YEAR>%s</YEAR>" % escapeText(ref.get("year","????")))
        if "journal" in ref:
            lines.append("<JOURNAL>%s</JOURNAL>" % escapeText(ref["journal"]))
        lines.append("</REFERENCE>")
        return lines

    def writeReferences(self, doc):
        """
        """
        lines=[]
        lines.append("<REFERENCELIST>")
        for ref in doc.data["references"]:
            lines.extend(self.writeReference(doc, ref))
        lines.append("</REFERENCELIST>")
        return lines

    def write(self, doc, filename):
        """
        """
        self.already_rendered=[]
        lines=[]
        lines.append('<?xml version="1.0" encoding="UTF-8"?>')
        lines.append('<!DOCTYPE PAPER SYSTEM "paper-structure-annotation.dtd">')

        lines.append("<PAPER>")
        lines.extend(self.writeMetadata(doc))
        lines.extend(self.writeAbstract(doc))
        lines.extend(self.writeBody(doc))
        lines.extend(self.writeReferences(doc))
        lines.append("</PAPER>")

        lines2=[]
        for line in lines:
            lines2.append(safe_unicode(line))

        lines=lines2
    ##    text="\n".join(lines)
        f=codecs.open(filename,"w", encoding="utf-8",errors="ignore")
    ##    f.writelines([line+"\n" for line in lines])
        f.writelines(lines)
        f.close()
    ##    return text

def saveSciXML(doc,filename):
    """
        Wrapper around SciXMLWriter to preserve backwards compatibility
    """
    writer=SciXMLWriter()
    writer.write(doc, filename)

def basicTest():
    """
    """
##    from azscixml import loadAZSciXML
    from scidoc import SciDoc

##    doc=loadAZSciXML(r"C:\NLP\PhD\bob\fileDB\jsonDocs\a00-1001.json")
    saveSciXML(doc,r"C:\NLP\PhD\bob\output\\"+doc["metadata"]["filename"]+".xml")
    pass

def main():
##    import db.corpora as cp
##    cp.useElasticCorpus()
    print(escapeText("balsdfbla & < >"))
    pass


if __name__ == '__main__':
    main()

