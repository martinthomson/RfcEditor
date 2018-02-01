import lxml.etree
from rfctools_common.parser import XmlRfc
from rfctools_common import log
import sys
from lxml.html import builder as E
from zzs import EditItem

try:
    import debug
    assert debug
except ImportError:
    pass


TextElements = [
    "bcp14", "br", "cref", "em", "eref", "iref", "strong", "relref", "sub",
    "sup", "tt", "xref", "vspace"
]
TextContainers = [
    "annotation", "area", "artwork", "blockquote", "city", "code", "country",
    "dd", "dt", "email", "keyword", "li", "organization",
    "phone", "postalline", "refcontent", "region", "sourcecode",
    "street", "t", "td", "th", "title", "uri", "workgroup",
    "c", "facsimile", "postamble", "preamble", "spanx", "ttcol"
]

diffCount = 0


def BuildDiffTree(xmlNode):
    """ Build the Diff tree from the xml tree """

    global diffCount

    if not isinstance(xmlNode, lxml.etree._ElementTree):
        sys.exit(2, "bad parameter")

    #  We have two problems here - the first is that lxml does
    #  not bother keeping the root elements as separate things
    #  so life is a pain

    diffCount = 0
    root = DiffDocument(xmlNode)

    # Grab nodes before the root
    element = xmlNode.getroot().getprevious()
    while element is not None:
        if element.tag is lxml.etree.PI:
            root.children.insert(0, DiffPI(element, root))

        element = element.getprevious()

    # Now process the root element itself
    root.children.append(root.createNode(xmlNode.getroot(), root))

    # Now process any elements after to root element

    element = xmlNode.getroot().getnext()
    while element is not None:
        if element.tag is lxml.etree.PI:
            root.children.append(DiffPI(element, root))

        element = element.getnext()

    return root


def DecorateSourceFile(diffRoot, sourceLines):
    diffRoot.decorateSource(sourceLines)


class DiffRoot(object):
    """ Root of the diff objects. """

    def __init__(self, xmlNode, parent):
        global diffCount

        self.xml = xmlNode
        self.children = []
        self.deleted = False
        self.inserted = False
        self.matchNode = None
        self.parent = parent
        diffCount += 1
        self.index = diffCount

    def ToString(self):
        node = E.DIV()
        node.text = "Need to override something"
        return node

    def ToHtml(self, parent):
        node = E.LI()
        node.text = "Need to override something"
        parent.append(node)

    @staticmethod
    def get_children(n):
        return n.children

    @staticmethod
    def InsertCost(left):
        item = EditItem(EditItem.OP_INSERT, None, left)
        item.cost = 1
        return item

    @staticmethod
    def DeleteCost(left):
        """ Compute the deletion cost of a node
            The deletion cost for an element needs to be higher
            that that for text so that doing a rename on texts
            is the preferred operation
        """
        item = EditItem(EditItem.OP_DELETE, left, None)
        if isinstance(left, DiffElement):
            item.cost = 10
        else:
            item.cost = 1
        return item

    @staticmethod
    def UpdateCost(left, right):
        #  If the types are not the same, then the cost is extremely high
        if type(left) is not type(right):
            item = EditItem(EditItem.OP_RENAME, left, right)
            item.cost = 100000
            return item
        return left.updateCost(right)

    def updateCost(self, right):
        item = EditItem(EditItem.OP_RENAME, self, right)
        item.cost = 100
        return item

    def _serialize(self, element):
        if sys.version > '3':
            return lxml.html.tostring(element, pretty_print=True, method='html',
                                      encoding='utf-8').decode('utf-8')
        else:
            return lxml.html.tostring(element, pretty_print=True, method='html')

    def markInsertTrees(self):
        insertTree = True
        for child in self.children:
            insertTree &= child.markInsertTrees()
        insertTree &= (self.matchNode is None)
        self.insertTree = insertTree
        return insertTree

    def createNode(self, xml, parent):
        if xml.tag is lxml.etree.PI:
            return DiffPI(xml, parent)
        textTest = "foo bar" + xml.tag
        return DiffElement(xml, parent)

    def getPredecessor(self, searchNode):
        prevSib = None
        for child in self.children:
            if searchNode.isMatchNode(child):
                return prevSib
            prevSib = child
        return None

    def getSuccessor(self, searchNode):
        found = False
        for child in self.children:
            if found:
                return child
            if searchNode.isMatchNode(child):
                found = True

        return None

    def isMatchNode(self, other):
        if self == other:
            return True
        if self.deleted:
            if len(self.children) != 1:
                return False
            return self.children[0].isMatchNode(other)
        if other.deleted:
            if len(other.children) != 1:
                return False
            return self.isMatchNode(other.children[0])
        return False

    def insertAfter(self, siblingNode, newNode):
        """ Insert newNode after siblingNode """
        i = 0
        for child in self.children:
            if siblingNode.isMatchNode(child):
                break
            i += 1
        if i == len(self.children):
            self.children.append(newNode)
        else:
            self.children.insert(i+1, newNode)

    def insertBefore(self, siblingNode, newNode):
        i = 0
        for child in self.children:
            if siblingNode.isMatchNode(child):
                break
            i += 1
        if i == len(self.children):
            # assert false
            self.children.append(newNode)
        else:
            self.children.insert(i, newNode)


class DiffDocument(DiffRoot):
    """ Represent the XML document.  We want to have a common
        node type that is always at the root for comparisions
    """

    def __init__(self, xmlNode):
        DiffRoot.__init__(self, xmlNode, None)

    def ToString(self):
        result = E.DIV()
        result.attrib['class'] = 'center'
        result.attrib['id'] = 'jstree_demo_div'

        ul = E.UL()
        result.append(ul)
        ul.attrib['class'] = 'jstree-open'

        for child in self.children:
            child.ToHtml(ul)

        return self._serialize(result)

    def updateCost(self, right):
        item = EditItem(EditItem.OP_MATCH, self, right)
        item.cost = 0
        return item

    def decorateSource(self, sourceLines):
        for child in self.children:
            child.decorateSource(sourceLines)

    def applyEdits(self, editList):
        newEdits = []
        for edit in editList:
            if edit.operation == EditItem.OP_DELETE:
                edit.left.deleted = True
            elif edit.operation == EditItem.OP_MATCH:
                edit.left.matchNode = edit.right
                edit.right.matchNode = edit.left
            elif edit.operation == EditItem.OP_RENAME:
                edit.left.matchNode = edit.right
                edit.right.matchNode = edit.left
            else:
                newEdits.append(edit)

        self.matchNode.markInsertTrees()

        while True:
            editList = newEdits
            newEdits = []

            for edit in editList:
                # Already processed
                if edit.right.matchNode is not None:
                    continue

                if edit.right.insertTree:
                    matchingParent = edit.right.parent.matchNode
                    if matchingParent is None:
                        # we don't know where it goes yet
                        newEdits.append(edit)
                        continue

                    # If a node has no children, then we can add it as a child
                    if edit.right.parent.matchNode.children is None or \
                       len(edit.right.parent.matchNode.children) == 0:
                        if edit.right.parent.matchNode.children is None:
                            edit.right.parent.matchNode.children = []
                        edit.right.parent.matchNode.children.append(
                            edit.right.cloneTree(edit.right.parent.matchNode))
                        continue

                    # If we have a matched preceeding node, put it after that one
                    sibling = edit.right.parent.getPredecessor(edit.right)
                    if sibling is not None:
                        if sibling.matchNode is not None:
                            newNode2 = edit.right.cloneTree(matchingParent)
                            matchingParent.insertAfter(sibling.matchNode, newNode2)
                            continue

                    # If we have a matching successor node, put it after that one
                    sibling = edit.right.parent.getSuccessor(edit.right)
                    if sibling is not None:
                        if sibling.matchNode is not None:
                            newNode2 = edit.right.cloneTree(matchingParent)
                            matchingParent.insertBefore(sibling.matchNode, newNode2)
                            continue

                    # If all of the left children are deleted and a new right is added.
                    allDeleted = True
                    for child in matchingParent.children:
                        if not child.deleted:
                            allDeleted = False
                            break

                    if allDeleted:
                        newNode2 = edit.right.cloneTree(matchingParent)
                        matchingParent.children.append(newNode2)
                        continue

                    newEdits.append(edit)
                    continue

                # Nodes which have undealt with children are deferred
                f = True
                for child in edit.right.children:
                    if child.matchNode is None and not child.insertTree:
                        f = False
                        break
                if not f:
                    newEdits.append(edit)
                    continue

                # Get the list of children that we need to match
                matchList = []
                for child in edit.right.children:
                    if not child.inserted and not child.insertTree:
                        matchList.append(child.matchNode)
                if len(matchList) == 0:
                    newEdits.append(edit)
                    continue

                # Build the list of all common ancestors of these nodes
                commonParents = None
                for child in matchList:
                    c = child.parent
                    ancestorList = []
                    while c is not None:
                        ancestorList.append(c)
                        c = c.parent
                    ancestorList = ancestorList[::-1]
                    if commonParents is None:
                        commonParents = ancestorList
                    else:
                        for i in range(min(len(ancestorList), len(commonParents))):
                            if ancestorList[i] != commonParents[i]:
                                commonParents = commonParents[:i]
                                break
                matchParent = commonParents[-1]

                # create the new node
                newNode = edit.right.clone()
                newNode.parent = matchParent
                newNode.inserted = True
                newNode.matchNode = edit.right
                edit.right.matchNode = newNode

                #

                i = 0
                iX = -1
                interums = []
                for child in edit.right.children:
                    if child.insertTree:
                        newNode2 = child.cloneTree(None)
                        newNode.children.append(newNode2)
                        continue
                    while i != len(matchParent.children):
                        if matchParent.children[i].isMatchNode(child.matchNode):
                            if len(interums) != 0:
                                if iX != -1:
                                    for ii in interums:
                                        newNode.children.append(matchParent.children[ii])
                                        matchParent.children[ii] = newNode
                                        del matchParent.children[ii]
                                        i -= 1
                                interums = []
                            newNode.children.append(matchParent.children[i])
                            matchParent.children[i].parent = newNode
                            del matchParent.children[i]
                            if iX == -1:
                                iX = i
                            break
                        else:
                            interums.append(i)
                        i += 1

                if iX == -1:
                    iX = 0
                matchParent.children.insert(iX, newNode)

            if len(editList) == len(newEdits):
                break

        print("Number of edits left = " + str(len(newEdits)))
        for edit in newEdits:
            print(edit.toString())


class DiffPI(DiffRoot):
    def __init__(self, xmlNode, parent):
        DiffRoot.__init__(self, xmlNode, parent)

    def ToHtml(self, parent):
        root = E.LI()
        parent.append(root)
        if self.inserted:
            root.attrib['class'] = 'right'
        elif self.deleted:
            root.attrib['class'] = 'left'
        elif self.matchNode is None:
            root.attrib['class'] = 'error'
        else:
            if self.xml.target == self.matchNode.xml.target:
                if self.xml.text == self.matchNode.xml.text:
                    pass
                else:
                    root.text = "<?{0} ".format(self.xml.target)
                    s = E.SPAN()
                    s.attrib['class'] = 'left'
                    s.text = self.xml.text
                    root.append(s)
                    s = E.SPAN()
                    s.attrib['class'] = 'right'
                    s.text = self.matchNode.xml.text
                    root.append(s)
                    s.tail = "?>"
                    return
            else:
                root.text = "<?"
                s = E.SPAN()
                s.attrib['class'] = 'left'
                s.text = self.xml.target
                root.append(s)
                s = E.SPAN()
                s.attrib['class'] = 'right'
                s.text = self.matchNode.xml.target
                root.append(s)
                s.tail = ' '
                s = E.SPAN()
                s.attrib['class'] = 'left'
                s.text = self.xml.text
                root.append(s)
                s = E.SPAN()
                s.attrib['class'] = 'right'
                s.text = self.matchNode.xml.text
                root.append(s)
                s.tail = "?>"
                return

        root.text = "<?{0} {1}?>".format(self.xml.target, self.xml.text)

    def cloneTree(self, parent):
        return DiffPI(self.xml, parent)

    def updateCost(self, right):
        if self.xml.target == right.xml.target:
            if self.xml.text == right.xml.text:
                return EditItem(EditItem.OP_MATCH, self, right)
            else:
                item = EditItem(EditItem.OP_RENAME, self, right)
                item.cost = 50
                return item
        item = EditItem(EditItem.OP_RENAME, self, right)
        item.cost = 100
        return item


class DiffElement(DiffRoot):
    def __init__(self, xmlNode, parent):
        if not isinstance(xmlNode, DiffElement):
            DiffRoot.__init__(self, xmlNode, parent)

            if xmlNode.text is not None:
                self.children.append(DiffText(xmlNode.text, self))

            for c in xmlNode.iterchildren():
                self.children.append(self.createNode(c, self))
                if c.tail is not None and c.tail.rstrip() != '':
                    self.children.append(DiffText(c.tail, self))
        else:
            DiffRoot.__init__(self, xmlNode.xml, parent)

    def cloneTree(self, root):
        clone = DiffElement(self, root)
        clone.matchNode = self
        clone.inserted = True
        self.matchNode = clone

        for child in self.children:
            clone.children.append(child.cloneTree(clone))
        return clone

    def clone(self):
        clone = DiffElement(self, None)
        return clone

    def ToHtml(self, parent):
        root = E.LI()
        parent.append(root)
        root.attrib['class'] = 'jstree-open'
        anchor = E.A()
        anchor.attrib["href"] = '#'
        root.append(anchor)
        if self.deleted:
            anchor.attrib['onclick'] = 'return sync2here(1, {0}, -1, 0)'.format(self.xml.sourceline)
            node = E.SPAN()
            node.attrib["class"] = 'left'
            node.text = "<" + self.xml.tag
            anchor.append(node)
            if len(self.xml.attrib):
                for key in self.xml.attrib.iterkeys():
                    node.text = node.text + " " + key + '="' + self.xml.attrib[key] + '"'
        elif self.inserted:
            anchor.attrib['onclick'] = 'return sync2here(-1, 0, 1, {0})'.format(self.xml.sourceline)
            node = E.SPAN()
            node.attrib['class'] = 'right'
            node.text = "<" + self.xml.tag
            anchor.append(node)
            if len(self.xml.attrib):
                for key in self.xml.attrib.iterkeys():
                    node.text = node.text + " " + key + '="' + self.xml.attrib[key] + '"'
        elif self.matchNode is None:
            anchor.attrib['onclick'] = 'return sync2here(1, {0}, -1, 1)'.format(self.xml.sourceline)
            node = E.SPAN()
            node.attrib['class'] = 'error'
            node.text = "<" + self.xml.tag
            anchor.append(node)
            if len(self.xml.attrib):
                for key in self.xml.attrib.iterkeys():
                    node.text = node.text + " " + key + '="' + self.xml.attrib[key] + '"'
        else:
            anchor.attrib['onclick'] = 'return sync2here(1, {0},  1, {1})' \
                  .format(self.xml.sourceline, self.matchNode.xml.sourceline)
            if self.xml.tag == self.matchNode.xml.tag:
                anchor.text = "<" + self.xml.tag
            else:
                anchor.text = "<"
                node = E.SPAN()
                node.attrib['class'] = 'left'
                node.text = self.xml.tag
                anchor.append(node)
                node = E.SPAN()
                node.attrib['class'] = 'right'
                node.text = self.matchNode.xml.tag
                anchor.append(node)
            if len(self.xml.attrib):
                for key in self.xml.attrib.iterkeys():
                    if key in self.matchNode.xml.attrib and \
                       self.xml.attrib[key] == self.matchNode.xml.attrib[key]:
                        node = E.SPAN()
                        node.text = " " + key + '="' + self.xml.attrib[key] + '"'
                        anchor.append(node)
                    else:
                        node = E.SPAN()
                        node.attrib['class'] = 'left'
                        node.text = " " + key + '="' + self.xml.attrib[key] + '"'
                        anchor.append(node)
                        if key in self.matchNode.xml.attrib:
                            node = E.SPAN()
                            node.attrib['class'] = 'right'
                            node.text = " " + key + '="' + self.matchNode.xml.attrib[key] + '"'
                            anchor.append(node)
            for key in self.matchNode.xml.attrib.iterkeys():
                if key not in self.xml.attrib:
                    node = E.SPAN()
                    node.attrib['class'] = 'right'
                    node.text = " " + key + '="' + self.matchNode.xml.attrib[key] + '"'
                    anchor.append(node)

        if len(self.children):
            s = E.SPAN()
            s.text = ">"
            if self.deleted:
                s.attrib['class'] = 'left'
            elif self.inserted:
                s.attrib['class'] = 'right'
            anchor.append(s)
            ul = E.UL()
            for child in self.children:
                child.ToHtml(ul)

            li = E.LI()
            li.attrib['class'] = 'jstree-open'
            li.text = "</" + self.xml.tag + ">"
            if self.deleted:
                li.attrib['class'] += ' left'
            elif self.inserted:
                li.attrib['class'] += ' right'
            ul.append(li)
            root.append(ul)
        else:
            s = E.SPAN()
            s.text = "/>"
            if self.deleted:
                s.attrib['class'] = 'left'
            elif self.inserted:
                s.attrib['class'] = 'right'
            anchor.append(s)

    def updateCost(self, right):
        if self.xml.tag == right.xml.tag:
            return EditItem(EditItem.OP_MATCH, self, right)
        item = EditItem(EditItem.OP_RENAME, self, right)
        item.cost = 100
        return item

    def decorateSource(self, sourceLines):
        source = sourceLines[self.xml.sourceLine]
        if self.deleted:
            pass
        elif self.inserted:
            pass
        elif self.matchNode is None:
            pass
        else:
            if self.xml.tag != self.matchNode.xml.tag:
                source.replace("&amp;"+self.xml.tag, "<span class='left'>&amp;" + self.xml.tag)

        sourceLines[self.xml.sourceLine] = source


class DiffText(DiffRoot):
    def __init__(self, text, parent):
        DiffRoot.__init__(self, None, parent)
        self.text = text

    def cloneTree(self, parent):
        clone = DiffText(self.text, parent)
        clone.matchNode = self
        clone.inserted = True
        self.matchNode = clone
        return clone

    def ToHtml(self, parent):
        node = E.LI()
        parent.append(node)
        if self.deleted:
            n = E.SPAN()
            n.attrib["class"] = 'left'
            n.text = self.text
            node.append(n)
        elif self.inserted:
            n = E.SPAN()
            n.attrib["class"] = 'right'
            n.text = self.text
            node.append(n)
        elif self.matchNode is None:
            n = E.SPAN()
            n.attrib["class"] = 'error'
            n.text = self.text
            node.append(n)
        else:
            if self.text == self.matchNode.text:
                node.text = self.text
            else:
                n = E.SPAN()
                n.attrib['class'] = 'left'
                n.text = self.text
                node.append(n)
                n = E.SPAN()
                n.attrib['class'] = 'right'
                n.text = self.matchNode.text
                node.append(n)

    def updateCost(self, right):
        if self.text == right.text:
            return EditItem(EditItem.OP_MATCH, self, right)
        item = EditItem(EditItem.OP_RENAME, self, right)
        item.cost = 3
        return item

    def decorateSource(self, sourceLines):
        pass