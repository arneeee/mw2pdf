"""Build all the desired documents from the Sonata wiki.
"""

# configuration:
import config

# imports:

import os, re, string, shutil
import wikiFetcher
import subprocess
import pypandoc
import mwclient
from pprint import pprint as pp


def ensure_dir(path):
    try:
        os.makedirs(path)
    except OSError:
        if not os.path.isdir(path):
            raise

def linesFromBulletlist(t):
    """Assume t is a mediawiki bullet list produced by readlines,
    one item per line. 
    Return a list of the items, without the bullet syntax.
    """
    r = [re.sub(' *\* *', '', x, count=1) for x in t]
    print r
    return r
    
def download(target, output, category=None):
    # return
    wikiFetcher.download(host=config.WIKIROOT,
                         target=target,
                         user=config.USER,
                         password=config.PASSWORD,
                         output=output,
                         category=category)


def processUML(doc, directory):
    """extract any included UML, put them in the UML dir,
    write the reduced document back with an input command"""

    print "UMLing ", doc, " in ", directory

    filename = os.path.join(directory,
                            doc + '.md')
    umldir = os.path.join(
        os.path.abspath(os.path.join(directory,
                                     os.pardir)),
        'uml')

    print filename, umldir

    # read the file:
    with open(filename, 'r') as f:
        data = f.read()

    i = 1
    m = re.search("<uml>(.*?)</uml>", data, re.S)
    while (m):
        umlfile = doc + "_" + str(i)
        with open(os.path.join(umldir,
                               umlfile + '.uml'),
                  'w') as umlhandle:
            umlhandle.write("@startuml")
            umlhandle.write(m.group(1))
            umlhandle.write("@enduml")

        # trigger the generation of the actual UML figure
        subprocess.call(['java',
                         '-jar',
                         '../../plantuml.jar',
                         '-tpng',
                         umlfile+'.uml'],
                        cwd=umldir)

        data = string.replace(data, m.group(0),
                              "[[File:" + umlfile + ".png|UML diagram]]", 1)
        i += 1
        m = re.search("<uml>(.*?)</uml>", data, re.S)

    with open(filename, 'w') as f:
        f.write(data)


def processPandoc(doc, directory):
    print "pandoc ", doc, directory

    filename = os.path.join(directory,
                            doc + '.md')

    outfile = os.path.join(
        os.path.join(
            os.path.abspath(os.path.join(directory,
                                         os.pardir)),
            'tex'),
        doc + '.tex')

    filters=[os.path.join(
        os.getcwd(),
        'linkFilter.py'),
         ]

    output = pypandoc.convert(filename,
                              format='mediawiki',
                              to='latex',
                              filters=filters,
                              outputfile=outfile)
    print output
    assert output == ""


def processFile(doc, directory):
    """process file doc in directory. Currently defined processing steps:
    - extract an included umls and run them thorugh plant uml
    - run pandoc on the remaining file
    """

    processUML(doc, directory)
    processPandoc(doc, directory)


def processLatex(docname, filelist):
    # put the latex main document into the directory
    shutil.copy('templates/main.tex',
                os.path.join(docname,
                             'tex'))

    # write the include instructions for the chapters:
    with open(os.path.join(docname,
                           'tex',
                           'includer.tex'),
              'w') as includer:
        
        for f in filelist:
            includer.write('\\include{' + f + '}')

    # run latx
    print os.path.join(docname, 'tex')
    try:
        subprocess.check_output(
            ['pdflatex',
             '-interaction=nonstopmode',
             'main.tex'],
            stderr=subprocess.STDOUT,
            cwd=os.path.join(docname, 'tex'),
        )
        e = None
    except subprocess.CalledProcessError as e:
        print e, e.output
        pass
    except Exception as e:
        print e

    return e


def processDocument(docname):
    print docname
    download(target=docname,
             output=docname)

    ensure_dir(os.path.join(docname, 'figures'))
    ensure_dir(os.path.join(docname, 'uml'))
    ensure_dir(os.path.join(docname, 'md'))
    ensure_dir(os.path.join(docname, 'tex'))

    filelist = []
    
    # now grab the files for this document:
    with open(os.path.join(docname,
                           docname + '.md'),
              'r') as doctoc:
        for doc in linesFromBulletlist(doctoc.readlines()):
            doc = doc.strip()
            print "processing: >>", doc, "<<"
            mddir = os.path.join(docname, 'md')
            download(target=doc,
                     output=mddir)

            # process each document separately
            processFile(doc, mddir)
            filelist.append(doc)

    e = processLatex(docname, filelist)

    return e

    # report the results back: stdout, pdf file


def uploadDocument(doc, excp):
    """upload both build progress information
    as well as a potneitally generated PDF """

    wikisite = mwclient.Site(config.WIKIROOT, path='/')
    wikisite.login(config.USER, config.PASSWORD)

    # deal with any possible exceptions 

    # deal with the PDF file: 
    texdir = os.path.join(doc, 'tex')
    pdffile = os.path.join(texdir,
                           'main.pdf')

    if os.path.isfile(pdffile):
        uploadedName = doc + ".pdf"
        print "pdf exists, uploding ", pdffile, " as ", uploadedName
        res = wikisite.upload(open(pdffile),
                              uploadedName,
                              "Generated file for document " + doc,
                              ignore=True)
        pp(res)
    else:
        print "no pdf to upload"

    #prepare the build report page
    page = wikisite.Pages[ doc  + 'BuildReport']
    text = page.text()
    text = "= Build report for {} =\n".format(doc)

    if excp:
        text += "== Return code ==\n"
        text += str(excp.returncode)
        text += "\n== Output ==\n"
        text += "\n<nowiki>\n"
        text += excp.output
        text += "\n</nowiki>\n"
    else:
        text += "\n== No errors reported! ==\n"

    text += "\n== PDF file ==\n"
    text += "\n[[File:" + doc + ".pdf]]\n"
    text += "\n[[Category:BuildReport]]\n"
    
    page.save(text)
    

def main():
    # start the download
    print "downloading documentlist"
    download(target=config.DOCUMENTLIST,
             output="Documentlist")

    # iterate over the documents contained in documentlist:
    with open(os.path.join('DocumentList',
                           config.DOCUMENTLIST + '.md'),
              'r') as f:
        for line in linesFromBulletlist(f.readlines()):
            e = processDocument(line)
            # uploadDocument(line, e)

if __name__ == '__main__':
    main()