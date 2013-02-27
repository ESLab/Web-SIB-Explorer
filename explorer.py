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

try:
    from flask import render_template, Flask, session, escape, request, redirect, g, url_for, jsonify, send_from_directory
    from flask.views import MethodView
    from werkzeug import secure_filename
except:
    print "You need to install Flask!\n" \
          "Either run 'pip -r requirements.txt' or 'pip install flask'"
    exit()

try:
    from flask.ext.sqlalchemy import SQLAlchemy
except:
    print "You need to install Flask-SQLAlchemy\n" \
          "Either run 'pip -r requirements.txt or 'pip install flask-sqlalchemy'"

try:
    import argparse
except:
    print "If you want to be able to pass arguments, please upgrade to Python >=2.7"

from signal import signal, SIGTERM
import atexit

from functools import wraps
from libs.sib_handler import *
import os
from uuid import uuid4


basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'wse.db')
db = SQLAlchemy(app)

UPLOAD_FOLDER = os.path.join(basedir ,"ontologies")
ALLOWED_EXTENSIONS = set(['rdf', 'owl'])
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024


SH = False

# DATABASE

# For storing information about subscriptions
class Subscription(db.Model):
    id = db.Column(db.String(150), primary_key=True)
    s = db.Column(db.String(150))
    p = db.Column(db.String(150))
    o = db.Column(db.String(150))
    added = db.Column(db.Integer)
    removed = db.Column(db.Integer)

    def __init__(self, id, s,p,o, added, removed):
        self.id = id
        self.s = s
        self.p = p
        self.o = o
        self.added = added
        self.removed = removed

    def __repr__(self):
        return 'Subscription...'


class Triple(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subscription = db.Column(db.String(150))
    s = db.Column(db.String(150))
    p = db.Column(db.String(150))
    o = db.Column(db.String(150))
    triple_type = db.Column(db.String(10))

    def __init__(self, subscription, s, p, o, triple_type):
        self.subscription = subscription
        self.s = str(s)
        self.p = str(p)
        self.o = str(o)
        self.triple_type = triple_type


    def __repr__(self):
        return 'Triple...'

# HELPER FUCNTIONS
def allowed_file(filename):
    return '.' in filename and\
           filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS

def cleanup():
    global SH
    if SH:
        subscriptions = Subscription.query.all()
        s = SH
        for subscription in subscriptions:
            try:
                s.unsubscribe(subscription.id)
            except Exception, e:
                print e

# SMART-M3

# The subscription handler
class SubHandler():
    def __init__(self, **kwargs):

        self.s = kwargs.get('subject',None)
        self.p = kwargs.get('predicate',None)
        self.o = kwargs.get('object',None)
        self.id = kwargs.get('id',str(uuid4()))


        self.subscription = Subscription(self.id, self.s, self.p, self.o, 0, 0,)
        db.session.add(self.subscription)
        db.session.commit()

    def handle(self, added, removed):
        subscription = Subscription.query.filter_by(id=self.id).first()
        subscription.added += len(added)
        subscription.removed += len(removed)
        db.session.commit()

        for trip in added:
            triple = Triple(self.id, trip[0], trip[1], trip[2], "1")
            db.session.add(triple)
            db.session.commit()
        for trip in removed:
            triple = Triple(self.id, trip[0], trip[1], trip[2], "0")
            db.session.add(triple)
            db.session.commit()


# DECORATORS

# Check if the user has set a IP for the SIB
def check_ip(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('sib_ip', False):
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# TEMPLATE TAGS

# Tags for removing the name-space and coloring
@app.context_processor
def triple_processor():
    def removeNS(single):
        if "#" in single:
            return single.partition("#")[2]
        return single

    def colorSingle(single):
        if "#" in single:
            ns,obj = single.split("#")
            return "<span class='single_ns'>"+ns+"#</span><span class='single_obj'>"+obj+"</span>".encode('ascii', 'xmlcharrefreplace')
        return single

    return dict(removeNS=removeNS, colorSingle=colorSingle)



# VIEW FUNCTIONS

# Index page
@app.route('/')
def index():
    return render_template('home.html')

# Tests a connection to the SIB and sets the correct session vars
# Using a global SH var for getting the same SIB handler across functions
@app.route('/sib/connection', methods=['POST', 'GET'])
def sibConnection():
    global SH
    if request.method == 'POST':
        s = SIBHandler(request.form['sib_ip'])
        if s.testConnection():
            count = s.countAllTriples()
            if count:
                session['triple_count'] = int(count[0][0][2])
            session['sib_ip'] = request.form['sib_ip']
            SH = s
            try:
                os.remove(os.path.join(basedir, 'wse.db'))
                db.create_all()
            except Exception, e:
                db.create_all()

        else:
            session['sib_ip'] = False
    return redirect(url_for('index'))


# List all triples
@app.route('/list/all/')
@check_ip
def listAll():
    s = SIBHandler(session['sib_ip'])
    entries = s.getAllTriples()
    return render_template('list_all.html', entries=entries)

# Get all triples as JSON
@app.route('/get/all/')
@check_ip
def getAll():
    triples={'subjects':["None"], 'predicates':["None"], 'objects':["None"]}
    s = SIBHandler(session['sib_ip'])
    entries = s.getAllTriples(limit=400)

    for entry in entries:
        if entry[0][2] not in triples['subjects']:
            triples['subjects'].append(entry[0][2])
        if entry[1][2] not in triples['predicates']:
            triples['predicates'].append(entry[1][2])
        if entry[2][2] not in triples['objects']:
            triples['objects'].append(entry[2][2])

    return jsonify(success=True, triples=triples, pred=triples['predicates'])

# List all classes
@app.route('/list/classes/')
@check_ip
def listClasses():
    s = SIBHandler(session['sib_ip'])
    entries = s.getAllClasses()
    return render_template('list_classes.html', entries=entries)

# List all properties
@app.route('/list/properties/')
@check_ip
def listProperties():
    s = SIBHandler(session['sib_ip'])
    entries = s.getAllProperties()
    return render_template('list_properties.html', entries=entries)

# List class tree
@app.route('/list/classes/tree')
@check_ip
def listClassesFull():
    s = SIBHandler(session['sib_ip'])
    entries = s.getFullClassInfo()
    return render_template('list_classes_tree.html', entries=entries)

# Removes a "object" from the class tree
@app.route('/object/remove', methods=['POST'])
@check_ip
def objectRemove():
    success = False
    if request.method == 'POST':
        object = request.form.get('object', False)
        if object:
            s = SIBHandler(session['sib_ip'])
            s.removeObject(object)
            success = True

    return jsonify(success=success)


# For showing query template and for querying
@app.route('/query', methods=['GET', 'POST'])
@check_ip
def querySIB():
    table_header = False
    entries = False
    error = False
    query = False
    time = False
    triples = False
    if request.method == 'POST':
        s = SIBHandler(session['sib_ip'])
        query = request.form['query']
        entries,error,time = s.querySIB(query)
        triples=len(entries)
        if entries:
            table_header = [column[0] for column in entries[0]]
    return render_template('querySIB.html', table_header=table_header, entries=entries, error=error, query=query, time=str(time), triples=triples)


# List subscriptions and creates subscriptions
@app.route('/subscriber', methods=['GET', 'POST'])
@check_ip
def subscriber():
    global SH
    success = False
    if request.method == 'POST':
        #s = SIBHandler(session['sib_ip'])
        s = SH

        subject = request.form['subject']
        if not subject: subject = "None"

        predicate = request.form['predicate']
        if not predicate: predicate = "None"

        object = request.form['object']
        if not object: object = "None"

        s.subscribe(subject, predicate, object, uuid4())

    subscriptions = Subscription.query.all()

    return render_template('subscriber.html', subscriptions=subscriptions)

# Close an existing subscription
@app.route('/subscription/close', methods=['POST'])
@check_ip
def subscription_close():
    global SH
    success = False
    if request.method == 'POST':
        try:
            subscription = Subscription.query.filter_by(id=request.form['subscription_id']).first()
            #s = SIBHandler(session['sib_ip'])
            s = SH
            if s.unsubscribe(subscription.id):
                db.session.delete(subscription)
                db.session.commit()
                success = True

            triples = Triple.query.filter_by(subscription=request.form['subscription_id'])
            for triple in triples:
                db.session.delete(triple)
            db.session.commit()

        except Exception,e:
            print e


    return jsonify(success=success)

# Updates the subscription list, returns JSON
@app.route('/subscriber/update', methods=['GET'])
@check_ip
def subscriber_update():
    success = False
    response = []

    subscriptions = Subscription.query.all()
    for subscription in subscriptions:
        response.append({'id':subscription.id, 'added':str(subscription.added), 'removed':str(subscription.removed)})

    return jsonify(success=success, subscriptions=response)

# Returns added triples as a paginated page
@app.route('/subscriber/<string:subscription>/<string:triple_type>/<int:page>', methods=['GET'])
@check_ip
def subscriber_triples(subscription=False, triple_type="added", page=1):
    if triple_type == "added":
        triples = Triple.query.filter_by(subscription=subscription, triple_type="1").paginate(page,20,False)
    else:
        triples = Triple.query.filter_by(subscription=subscription, triple_type="0").paginate(page,20,False)

    subscription = Subscription.query.filter_by(id=subscription).first()

    return render_template('subscriber_triples.html', triples=triples, subscription=subscription, triple_type=triple_type)


# Benchmarking the SIB
@app.route('/sib/info', methods=['GET', 'POST'])
@check_ip
def sibInfo():
    info = False
    if request.method == 'POST':
        s = SIBHandler(session['sib_ip'])
        info = s.getSIBInfo()

    return render_template('sib_info.html', info=info)


# For file uploads
@app.route('/ontologies/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'],
        filename)

# Maintaining the SIB
@app.route('/sib/maintenance', methods=['GET', 'POST'])
@check_ip
def sib_maintenance():

    ontologies = os.listdir(UPLOAD_FOLDER)

    s = SIBHandler(session['sib_ip'])

    if request.method == 'POST':
        action = request.form.get('action', False)
        if action == 'upload':
            extension_ok = False
            upload_success = False
            ufile = request.files['file']
            if ufile and allowed_file(ufile.filename):
                extension_ok = True
                filename = secure_filename(ufile.filename)
                ufile.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                upload_success = True
            results = {'success':upload_success, 'extension':extension_ok}
            return jsonify(results=results)
        if action == 'clean':
            s.cleanSIB()
        if action == 'load':
            load_result = s.loadFile(os.path.join(app.config['UPLOAD_FOLDER'], request.form['selected']))
            results = {'success':load_result['result'], 'time':load_result['time']}
            return jsonify(results=results)

    global SH
    sh_info = {'member_of': SH.member_of, 'connections':SH.connections, 'node_id':SH.node_id, 'user_node_id':SH.user_node_id}

    return render_template('sib_maintenance.html', ontologies=ontologies, sh_info=sh_info)

@app.route('/sib/maintenance/get/uploads', methods=['GET', 'POST'])
@check_ip
def sib_maintenance_get_uploads():
    ontologies = os.listdir(UPLOAD_FOLDER)
    ontologies = {'files':ontologies}
    return jsonify(success=True, ontologies=ontologies)

@app.route('/sib/maintenance/get/info', methods=['GET'])
@check_ip
def sib_maintenance_get_info():
    s = SIBHandler(session['sib_ip'])
    count = s.countAllTriples()

    if count:
        session['triple_count'] = int(count[0][0][2])
        count = count[0][0][2]
    else:
        session['triple_count'] = 0
        count = 0

    info = {'count':str(count)}

    return jsonify(success=True, info=info)

app.secret_key = os.urandom(24)




@app.route('/changelog')
def changelog():
    return render_template('changelog.html')

if __name__ == '__main__':
    atexit.register(cleanup)
    signal(SIGTERM, lambda signum, stack_frame: exit(1))
    #app.run(host='127.0.0.1', debug=True)


    try:
        parser = argparse.ArgumentParser()
        parser.add_argument("-ip", "--ip", help="IP to run the server on",
                            type=str)
        parser.add_argument("-p", "--port", help="Port to run the server on",
                            type=str)
        args = parser.parse_args()
        if args.port: args.port = int(args.port)

        if args.ip and args.port:
            app.run(host=args.ip, port=args.port, debug=True)
        elif args.ip:
            app.run(host=args.ip, port=5000, debug=True)
        elif args.port:
            app.run(host='127.0.0.1', port=args.port, debug=True)
        else:
            app.run(host='127.0.0.1', port=5000, debug=True)

    except Exception,e:
        app.run(host='127.0.0.1', port=5000, debug=True)





