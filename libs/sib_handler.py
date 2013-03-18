# -*- coding: utf-8 -*-

"""
Web SIB Explorer created by Frank Wickström at the Embedded systems lab at Åbo Akademi University
Copyright (C) 2012  Frank Wickström

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

from smart_m3.m3_kp import *
import collections
import sys
import time
import explorer

class SimpleSubHandler():
    def handle(self, added, removed):
        pass

class Smart(KP):
    def __init__(self, server_ip="127.0.0.1", server_port=10010, kp_name="SIBExplorer"):
        KP.__init__(self, kp_name)

        self.ss_handle = ("X", (TCPConnector, (server_ip,
                                               server_port)))

        self.init_dict = {}

        self.subscriptions = []

        self.send_list = []
        self.remove_list = []
        self.update_list = []

        self.new = True

    def join_sib(self):
        try:
            self.join(self.ss_handle)
            return True
        except Exception, e:
            return False

    def leave_sib(self):
        for subscription in self.subscriptions:
            self.CloseSubscribeTransaction(subscription['subscription'])

        self.leave(self.ss_handle)

    def sparql_query(self, sparql):
        result = False

        PREFIXES = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/02/rdf-schema#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
            """
        q = PREFIXES+sparql

        qt = self.CreateQueryTransaction(self.ss_handle)
        result = qt.sparql_query(q)

        self.CloseQueryTransaction(qt)

        return result

    def insert(self, triples, send=True, file=False):
        ins = self.CreateInsertTransaction(self.ss_handle)
        if file:
            ins.send(triples, encoding = "RDF-XML", confirm = True)
        else:
            insert_triple = triples
            ins.send(insert_triple, confirm = True)
        self.CloseInsertTransaction(ins)
        return True

    def simple_subscribe(self, s=None,p=None,o=None):
        if s: s = URI(s)
        if p: p = URI(p)
        if o: o = URI(o)
        st = self.CreateSubscribeTransaction(self.ss_handle)
        st.subscribe_rdf([Triple(s, p, o)], SimpleSubHandler)
        self.subscriptions.append({'subscription':st})
        return st

    def subscribe(self, s=None,p=None,o=None,id=None):
        if s.lower() == "none":
            s = None
        else:
            s = URI(s)
        if p.lower() == "none":
            p = None
        else:
            p = URI(p)
        if o.lower() == "none":
            o = None
        else:
            o = URI(o)

        if id:
            id = str(id)

        st = self.CreateSubscribeTransaction(self.ss_handle)
        st.subscribe_rdf([Triple(s, p, o)], explorer.SubHandler(subject=str(s), predicate=str(p), object=str(o), id=id, sub_type='rdf'))
        self.subscriptions.append({'subscription':st, 'id':id})

        return st

    def subscribe_sparql(self, sparql_query,id=None):

        if id:
            id = str(id)

        st = self.CreateSubscribeTransaction(self.ss_handle)
        st.subscribe_sparql(sparql_query, explorer.SubHandler(sparql_query=sparql_query, id=id, sub_type='sparql'))
        self.subscriptions.append({'subscription':st, 'id':id})

        return st

    def unsubscribe(self, id):
        # map+itemgetter might be more efficient here, but KISS...
        for subscription in self.subscriptions:
            if subscription['id'] == id:
                self.CloseSubscribeTransaction(subscription['subscription'])
                return True
        return False


    def save(self):
        self.join_sib()
        result = self.insert(self.send_list)
        self.leave_sib()
        return result

    def remove(self, triples, send=True):
        try:
            rem = self.CreateRemoveTransaction(self.ss_handle)
            remove_triple = triples
            rem.remove(remove_triple)
            self.CloseRemoveTransaction(rem)
            return True
        except:
            return False

class TreeNode():
    def __init__(self, name= "", parent= None, children= []):
        self.parent = parent
        self.children = children
        self.name = name

    def addChild(self, child):
        self.children.append(child)


class Updater():
    def __init__(self, node):
        self.state = False

class SIBHandler(Smart):
    def __init__(self, sib_ip):
        if ":" in sib_ip:
            ip,port = sib_ip.split(':')
        else:
            ip = sib_ip
            port = 10010
        Smart.__init__(self,server_ip=ip, server_port=int(port),kp_name="SIBHandler")
        self.connection = self.join_sib()

    def testConnection(self):
        return self.connection

    def countAllTriples(self):
        sparql = """SELECT (COUNT(?s) AS ?no) { ?s ?p ?o  }"""

        return self.sparql_query(sparql)

    def getAllTriples(self, limit=None):
        sparql = """SELECT ?s ?p ?o WHERE {
                    ?s ?p ?o }
            """
        if limit:
            sparql += "LIMIT "+str(limit)
        return self.sparql_query(sparql)

    def getAllClasses(self):
        sparql = """SELECT ?subject
	                WHERE { ?subject rdf:type rdfs:Class }
        """

        entries = self.sparql_query(sparql)

        classes = []

        for entry in entries:
            classes.append(entry[0][2])

        return sorted(classes)

    def getAllProperties(self):
        sparql = """SELECT ?p
	                WHERE { ?s ?p ?o }
        """
        entries = self.sparql_query(sparql)

        properties = []

        for entry in entries:
            if not entry[0][2] in properties:
                properties.append(entry[0][2])

        return sorted(properties)

    def getFullClassInfo(self):
        filters = ['http://www.w3.org/1999/02/22-rdf-syntax-ns#',
                  'http://www.w3.org/2001/XMLSchema#',
                  'http://www.w3.org/2000/01/rdf-schema#',
                  'http://www.w3.org/2000/02/rdf-schema#']
        filters= []

        sparql = """SELECT ?subject
	                WHERE { ?subject rdf:type rdfs:Class }
	                ORDER BY ?subject"""

        entries = self.sparql_query(sparql)

        tree = collections.OrderedDict()

        for entry in entries:
            tree[entry[0][2]] = collections.OrderedDict()
            sparql = """SELECT ?s
                        WHERE { ?s ?p <"""+entry[0][2].encode('utf-8')+"""> }
                        ORDER BY ?s"""

            sub_entry = self.sparql_query(sparql)

            for entry_2 in sub_entry:
                tree[entry[0][2]][entry_2[0][2]] = collections.OrderedDict()

                sparql = """SELECT ?p ?o
                            WHERE { <"""+entry_2[0][2].encode('utf-8') +"""> ?p ?o}
                            ORDER BY ?p"""

                sub_sub_entry = self.sparql_query(sparql)

                for entry_3 in sub_sub_entry:
                    filter = False
                    for item in filters:
                        if item in entry_3[0][2]:
                            filter = True
                            break

                    if not filter: tree[entry[0][2]][entry_2[0][2]][entry_3[0][2]] = entry_3[1][2]

        return tree

    def removeObject(self, object):
        triples = [Triple(URI(object), None, None),
                   Triple(None, None, URI(object))]
        self.remove(triples)

    def cleanSIB(self):
        triple = [Triple(None, None, None)]
        self.remove(triple)

    def loadFile(self, file_path):
        if sys.platform == "win32":
            timer = time.clock
        else:
            timer = time.time
        try:
            t0 = timer()
            self.insert(file_path, file=True)
            t1 = timer()
            return {'time':t1-t0, 'result':True}

        except Exception, e:
            return {'time':-1, 'result':False, 'error':e}


    def timeIt(self, f):
        if sys.platform == "win32":
            timer = time.clock
        else:
            timer = time.time
        t0 = timer()
        result = f()
        t1 = timer()
        return [t1-t0, result]

    def timeQuery(self, q):
        if sys.platform == "win32":
            timer = time.clock
        else:
            timer = time.time
        t0 = timer()

        result = self.sparql_query(q)

        t1 = timer()
        return [t1-t0, result]

    def querySIB(self, query):
        sparql = query
        error = False

        time, entries = self.timeQuery(sparql)

        if entries == []:
            error = True

        return [entries, error, time]




    def getSIBInfo(self):

        info = []

        sparql = """SELECT ?s ?p ?o WHERE {
                    ?s ?p ?o }
            """
        t, triples = self.timeQuery(sparql)
        info.append({'name': "Getting all triples", 'time':t, 'length':len(triples)})


        sparql = """SELECT ?subject
	                WHERE { ?subject rdf:type rdfs:Class }
        """
        t, triples = self.timeQuery(sparql)
        info.append({'name': "Getting all classes", 'time':t, 'length':len(triples)})


        sparql = """SELECT ?p
	                WHERE { ?s ?p ?o }
        """
        t, triples = self.timeQuery(sparql)
        info.append({'name': "Getting all properties", 'time':t, 'length':len(triples)})


        subscriptions = []

        if sys.platform == "win32":
            timer = time.clock
        else:
            timer = time.time

        t0 = timer()
        for i in range(0,100):
            subscriptions.append(self.simple_subscribe())
        t1 = timer()
        t_sub = t1-t0
        info.append({'name': "Creating 100 subscriptions", 'time':t_sub, 'length':"-"})

        t0 = timer()
        for subscription in subscriptions:
            self.CloseSubscribeTransaction(subscription)
        t1 = timer()
        t_unsub = t1-t0
        info.append({'name': "Closing 100 subscriptions", 'time':t_unsub, 'length':"-"})

        info.append({'name': "Creating and closing 100 subscriptions", 'time':t_sub+t_unsub, 'length':"-"})

        return info



