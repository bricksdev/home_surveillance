# WebApp
# Brandon Joffe
# 2016
#
# Copyright 2016, Brandon Joffe, All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from flask import Flask, render_template, Response, redirect, url_for, request, jsonify, send_file, session, g
from flask.ext.uploads import UploadSet, configure_uploads, IMAGES
import Camera
from flask.ext.socketio import SocketIO, send, emit 
import SurveillanceSystem
import json
import logging
from logging.handlers import RotatingFileHandler
import threading
import time
from random import random
import os
import sys
import cv2
import psutil
import httplib
import binascii

LOG_FILE = 'logs/WebApp.log'

# Initialises system variables, this object is the heart of the application
HomeSurveillance = SurveillanceSystem.SurveillanceSystem() 
# Threads used to continuously push data to the client
alarmStateThread = threading.Thread() 
facesUpdateThread = threading.Thread()
facesDetectingThread = threading.Thread()
monitoringThread = threading.Thread() 
alarmStateThread.daemon = False
facesUpdateThread.daemon = False
facesDetectingThread.daemon = False
monitoringThread.daemon = False
# Flask setup
app = Flask('SurveillanceWebServer')
app.config['SECRET_KEY'] = os.urandom(24) # Used for session management
socketio = SocketIO(app)
photos = UploadSet('photos', IMAGES)
app.config['UPLOADED_PHOTOS_DEST'] = 'uploads/imgs'
configure_uploads(app, photos)

# import sys
# sys.path.append('../pycharm-debug.egg')
#
# import pydevd
# pydevd.settrace('192.168.1.14', port=21000, stdoutToServer=True, stderrToServer=True)

@app.errorhandler(Exception)
def unhandled_exception(e):
    app.logger.error('Unhandled Exception: %s', str(e))
    return render_template('pages/examples/500.html'), 500

@app.route('/', methods=['GET','POST'])
def login():
    error = None
    if request.method == 'POST':
        session.pop('user',None) # Drops session everytime user tries to login
        if request.form['username'] != 'admin' or request.form['password'] != 'admin':
            error = 'Invalid username or password. Please try again'
        else:
            session['user'] = request.form['username']
            return redirect(url_for('home'))

    return render_template('login.html', error = error)

@app.route('/home')
def home():
    if g.user:
        return render_template('index.html')
    return redirect(url_for('login'))

@app.before_request
def before_request():
    """Initialise session"""
    g.user = None
    if 'user' in session:
        g.user = session['user']

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST' and 'photo' in request.files:
        try:
            filename = photos.save(request.files['photo'])
            image = request.files['photo']
            name = request.form.get('name')
            image = cv2.imread('uploads/imgs/' + filename)
            wriitenToDir = HomeSurveillance.add_face(name,image, upload = True)
            message = "file uploaded successfully"
        except:
             message = "file upload unsuccessfull"

        return render_template('index.html', message = message)
    if g.user:
        return render_template('index.html')
    else:
        return redirect(url_for('login'))

@app.route('/detecting', methods=['GET', 'POST'])
def detecting():
    message = None
    if request.method == 'POST' and 'photo' in request.files:
        try:
            filename = photos.save(request.files['photo'])
            image = request.files['photo']
            name = request.form.get('name')
            image = cv2.imread('uploads/imgs/' + filename)
            person = HomeSurveillance.detected_recoginer_face(image)
            message = "ditected successfully"

        except:
             message = "ditected unsuccessfull"

        return render_template('index.html', message = message, person= person)
    if g.user:
        return render_template('index.html')
    else:
        return redirect(url_for('login'))

@app.route('/adduser', methods=['POST'])
def adduser():
    data = {"success":False}
    message = None
    # token must validate if it is exits
    if 'apitoken' in request.headers and 'photo' in request.files:
        try:
            filename = photos.save(request.files['photo'])
            image = request.files['photo']
            name = request.form.get('name')
            image = cv2.imread('uploads/imgs/' + filename)
            wriitenToDir = HomeSurveillance.add_face(name,image, upload = True)
            message = "file uploaded successfully"
            data["success"]=True
        except:
            message = "file upload unsuccessfull"

    data["message"] = message
    #back json
    return jsonify(data)

@app.route('/detecte_face', methods=['POST'])
def detecte_face():
    data = {"success": False}
    message = None
    if request.method == 'POST' and 'photo' in request.files:
        try:
            filename = photos.save(request.files['photo'])
            image = request.files['photo']
            name = request.form.get('name')
            image = cv2.imread('uploads/imgs/' + filename)
            person = HomeSurveillance.detected_recoginer_face(image)


            if person is not None :
                data["success"] = True
                data["person"] = person.identity
                key, paths = HomeSurveillance.get_face_path_name(person.identity)
                data["photo_path"] = paths
                message = "ditected successfully"
            else:
                data["success"] = False
                message = "face Not found"
        except:
             message = "ditected unsuccessfull"

    data["message"] = message
    #back json
    return jsonify(data)

@app.route('/get_name_faces/<name>', methods=['POST',"GET"])
def get_name_faces(name):
    """Used to push all detected faces to client"""
    key, filename = name.split("-")
    img = HomeSurveillance.get_face_name(key, filename)
    return Response((b'--frame\r\n'
                     b'Content-Type: image/jpeg\r\n\r\n' + img + b'\r\n\r\n'),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

def gen(camera):
    """Can read processed frame or unprocessed frame.
    When streaming the processed frame with read_processed()
    and setting the drawing variable in the SurveillanceSystem 
    class, you can see all detection bounding boxes. This
    however slows down streaming and therefore read_jpg()
    is recommended"""
    while True:
        frame = camera.read_processed()    # read_jpg()  # read_processed()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')  # Builds 'jpeg' data with header and payload

@app.route('/video_streamer/<camNum>', methods = ['GET','POST'])
def video_streamer(camNum):
    """Used to stream frames to client, camNum represents the camera index in the cameras array"""
    return Response(gen(HomeSurveillance.cameras[int(camNum)]),
                    mimetype='multipart/x-mixed-replace; boundary=frame') # A stream where each part replaces the previous part the multipart/x-mixed-replace content type must be used.

def system_monitoring():
    """Pushes system monitoring data to client"""
    while True:
        cameraProcessingFPS = []
        for camera in HomeSurveillance.cameras:
    
            cameraProcessingFPS.append("{0:.2f}".format(camera.processingFPS))
            #print "FPS: " +str(camera.processingFPS) + " " + str(camera.streamingFPS)
            app.logger.info("FPS: " +str(camera.processingFPS) + " " + str(camera.streamingFPS))
        systemState = {'cpu':cpu_usage(),'memory':memory_usage(), 'processingFPS': cameraProcessingFPS}
        socketio.emit('system_monitoring', json.dumps(systemState) ,namespace='/surveillance')
        time.sleep(3)

def cpu_usage():
      psutil.cpu_percent(interval=1, percpu=False) #ignore first call - often returns 0
      time.sleep(0.12)
      cpu_load = psutil.cpu_percent(interval=1, percpu=False)
      #print "CPU Load: " + str(cpu_load)
      app.logger.info("CPU Load: " + str(cpu_load))
      return cpu_load  

def memory_usage():
     mem_usage = psutil.virtual_memory().percent
     #print "System Memory Usage: " + str( mem_usage)
     app.logger.info("System Memory Usage: " + str( mem_usage))
     return mem_usage 

@app.route('/add_camera', methods = ['GET','POST'])
def add_camera():
    """Adds camera new camera to SurveillanceSystem's cameras array"""
    if request.method == 'POST':
        try:
            camURL = request.form.get('camURL')
            application = request.form.get('application')
            detectionMethod = request.form.get('detectionMethod')
            fpsTweak = request.form.get('fpstweak')
            with HomeSurveillance.camerasLock :
                HomeSurveillance.add_camera(SurveillanceSystem.Camera.IPCamera(camURL,application,detectionMethod,fpsTweak))
            data = {"camNum": len(HomeSurveillance.cameras) -1}
            app.logger.info("Addding a new camera with url: ")
            app.logger.info(camURL)
            app.logger.info(fpsTweak)
            return jsonify(data)
        except Exception as e:
            app.logger.error("ERROR could not open camera %s",str(e))
            pass
    return render_template('index.html')

@app.route('/remove_camera', methods = ['GET','POST'])
def remove_camera():
    if request.method == 'POST':
        camID = request.form.get('camID')
        app.logger.info("Removing camera: ")
        app.logger.info(camID)
        data = {"camNum": len(HomeSurveillance.cameras) - 1}
        with HomeSurveillance.camerasLock:
            HomeSurveillance.remove_camera(camID)
        app.logger.info("Removing camera number : " + data)
        data = {"alert_status": "removed"}
        return jsonify(data)
    return render_template('index.html')

@app.route('/create_alert', methods = ['GET','POST'])
def create_alert():
    if request.method == 'POST':
        camera = request.form.get('camera')
        emailAddress = request.form.get('emailAddress')
        event = request.form.get('eventdetail')
        alarmstate = request.form.get('alarmstate')
        person = request.form.get('person')
        push_alert = request.form.get('push_alert')
        email_alert = request.form.get('email_alert')
        trigger_alarm = request.form.get('trigger_alarm')
        notify_police = request.form.get('notify_police')
        confidence = request.form.get('confidence')

        #print "unknownconfidence: " + confidence
        app.logger.info("unknownconfidence: " + confidence)

        actions = {'push_alert': push_alert , 'email_alert':email_alert , 'trigger_alarm':trigger_alarm , 'notify_police':notify_police}
        with HomeSurveillance.alertsLock:
            HomeSurveillance.alerts.append(SurveillanceSystem.Alert(alarmstate,camera, event, person, actions, emailAddress, int(confidence))) 
        HomeSurveillance.alerts[-1].id 
        data = {"alert_id": HomeSurveillance.alerts[-1].id, "alert_message": "Alert if " + HomeSurveillance.alerts[-1].alertString}
        return jsonify(data)
    return render_template('index.html')

@app.route('/remove_alert', methods = ['GET','POST'])
def remove_alert():
    if request.method == 'POST':
        alertID = request.form.get('alert_id')
        with HomeSurveillance.alertsLock:
            for i, alert in enumerate(HomeSurveillance.alerts):
                if alert.id == alertID:
                    del HomeSurveillance.alerts[i]
                    break
           
        data = {"alert_status": "removed"}
        return jsonify(data)
    return render_template('index.html')

@app.route('/remove_face', methods = ['GET','POST'])
def remove_face():
    if request.method == 'POST':
        predicted_name = request.form.get('predicted_name')
        camNum = request.form.get('camera')

        with HomeSurveillance.cameras[int(camNum)].peopleDictLock:
            try:
                del HomeSurveillance.cameras[int(camNum)].people[predicted_name]
                app.logger.info("==== REMOVED: " + predicted_name + "===")
            except Exception as e:
                app.logger.error("ERROR could not remove Face %s" , str(e))
                pass

        data = {"face_removed":  'true'}
        return jsonify(data)
    return render_template('index.html')

@app.route('/add_face', methods = ['GET','POST'])
def add_face():
    if request.method == 'POST':
        trust = request.form.get('trust')
        new_name = request.form.get('new_name')
        person_id = request.form.get('person_id')
        camNum = request.form.get('camera')
        img = None
        
        with HomeSurveillance.cameras[int(camNum)].peopleDictLock:  
            try:  
                img = HomeSurveillance.cameras[int(camNum)].people[person_id].face   # Gets face of person detected in cameras 
                predicted_name = HomeSurveillance.cameras[int(camNum)].people[person_id].identity
                del HomeSurveillance.cameras[int(camNum)].people[person_id]    # Removes face from people detected in all cameras 
            except Exception as e:
                app.logger.error("ERROR could not add Face %s " ,str( e))
 
        #print "trust " + str(trust)
        app.logger.info("trust " + str(trust))
        if str(trust) == "false":
            wriitenToDir = HomeSurveillance.add_face(new_name,img, upload = False)
        else:
            wriitenToDir = HomeSurveillance.add_face(predicted_name,img, upload = False)

        systemData = {'camNum': len(HomeSurveillance.cameras) , 'people': HomeSurveillance.peopleDB, 'onConnect': False}
        socketio.emit('system_data', json.dumps(systemData) ,namespace='/surveillance')
           
        data = {"face_added":  wriitenToDir}
        return jsonify(data)
    return render_template('index.html')

@app.route('/retrain_classifier', methods = ['GET','POST'])
def retrain_classifier():
    if request.method == 'POST':
        app.logger.info("retrain button pushed. clearing event in surveillance objt and calling trainingEvent")
        HomeSurveillance.trainingEvent.clear() # Block processing threads
        retrained = HomeSurveillance.recogniser.trainClassifier()#calling the module in FaceRecogniser to start training
        HomeSurveillance.trainingEvent.set() # Release processing threads       
        data = {"finished":  retrained}
        app.logger.info("Finished re-training")
        return jsonify(data)
    return render_template('index.html')

@app.route('/get_faceimg/<name>', methods = ['GET','POST'])
def get_faceimg(name):  
    key,camNum = name.split("_")
    try:
        with HomeSurveillance.cameras[int(camNum)].peopleDictLock:
            img = HomeSurveillance.cameras[int(camNum)].people[key].thumbnail
    except Exception as e:
        app.logger.error("Error %s" , str(e))
        img = ""

    if img == "":
        return "http://www.character-education.org.uk/images/exec/speaker-placeholder.png"            
    return  Response((b'--frame\r\n'
                     b'Content-Type: image/jpeg\r\n\r\n' + img + b'\r\n\r\n'),
                    mimetype='multipart/x-mixed-replace; boundary=frame') 

@app.route('/get_detecting_faceimg/<name>', methods = ['GET','POST'])
def get_detecting_faceimg(name):
    key,camNum = name.split("_")
    try:
        with HomeSurveillance.cameras[int(camNum)].peopleDictLock:
            img = HomeSurveillance.cameras[int(camNum)].people[key].origin_thumbnail
            # img = cv2.imdecode(img, cv2.IMREAD_UNCHANGED)
    except Exception as e:
        app.logger.error("Error %s", str(e))
        img = ""

    if img == "":
        conn = httplib.HTTPSConnection("http://www.character-education.org.uk/images/exec/speaker-placeholder.png")
        conn.request("GET", "/")
        r1 = conn.getresponse()
        print r1.status, r1.reason
        img = data1 = r1.read()

    data = img[:]
    return data.tostring()
    #return Response(img, mimetype='image/jpeg')
    # return  Response((b'--frame\r\n'
    #                  b'Content-Type: image/jpeg\r\n\r\n' + img + b'\r\n\r\n'),
    #                 mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/get_all_faceimgs/<name>', methods = ['GET','POST'])
def get_all_faceimgs(name):
    key, camNum, imgNum = name.split("_")
    try:
        with HomeSurveillance.cameras[int(camNum)].peopleDictLock:
            img = HomeSurveillance.cameras[int(camNum)].people[key].thumbnails[imgNum]
    except Exception as e:
        app.logger.error("Error %s" , str(e))
        img = ""

    if img == "":
        return "http://www.character-education.org.uk/images/exec/speaker-placeholder.png"            
    return  Response((b'--frame\r\n'
                     b'Content-Type: image/jpeg\r\n\r\n' + img + b'\r\n\r\n'),
                    mimetype='multipart/x-mixed-replace; boundary=frame') 

def update_faces():
    """Used to push all detected faces to client"""
    while True:
        try:
            peopledata = []
            persondict = {}
            thumbnail = None
            with HomeSurveillance.camerasLock :
                for i, camera in enumerate(HomeSurveillance.cameras):
                    with HomeSurveillance.cameras[i].peopleDictLock:
                        for key, person in camera.people.iteritems():
                            persondict = {'identity': key , 'confidence': person.confidence, 'camera': i, 'timeD':person.time, 'prediction': person.identity,'thumbnailNum': len(person.thumbnails)}
                            app.logger.info(persondict)
                            peopledata.append(persondict)


            socketio.emit('people_detected', json.dumps(peopledata) ,namespace='/surveillance')
        except Exception as e:
            app.logger.error("update faces Error %s", str(e))
        time.sleep(4)

def detecting_faces():
    """Used to push all detected faces to client"""
    while True:
        try:
            peopledata = []
            persondict = {}
            thumbnail = None
            with HomeSurveillance.camerasLock :
                for i, camera in enumerate(HomeSurveillance.cameras):
                    HomeSurveillance.get_face_frame(camera)
                    frame = camera.processing_frame
                    if not frame == None:
                        ret, frame = cv2.imencode('.jpg', frame)
                        nframe = binascii.b2a_base64(frame)
                        persondict = {'camera': i, 'frame':nframe}
                        app.logger.info(persondict)
                        peopledata.append(persondict)

            socketio.emit('person_detected', json.dumps(peopledata) ,namespace='/surveillance')
        except Exception as e:
            app.logger.error("update faces Error %s", str(e))
        time.sleep(4)

def alarm_state():
     """Used to push alarm state to client"""
     while True:
            alarmstatus = {'state': HomeSurveillance.alarmState , 'triggered': HomeSurveillance.alarmTriggerd }
            socketio.emit('alarm_status', json.dumps(alarmstatus) ,namespace='/surveillance')
            time.sleep(3)


@socketio.on('alarm_state_change', namespace='/surveillance') 
def alarm_state_change():   
    HomeSurveillance.change_alarm_state()

@socketio.on('panic', namespace='/surveillance') 
def panic(): 
    HomeSurveillance.trigger_alarm()
   

@socketio.on('my event', namespace='/surveillance') # socketio used to receive websocket messages, Namespaces allow a cliet to open multiple connections to the server that are multiplexed on a single socket
def test_message(message):   # Custom events deliver JSON payload
    emit('my response', {'data': message['data']}) # emit() sends a message under a custom event name

@socketio.on('my broadcast event', namespace='/surveillance')
def test_message(message):
    emit('my response', {'data': message['data']}, broadcast=True) # broadcast=True optional argument all clients connected to the namespace receive the message

                   
@socketio.on('connect', namespace='/surveillance') 
def connect(): 
    
    # Need visibility of global thread object                
    global alarmStateThread
    global facesUpdateThread
    global facesDetectingThread
    global monitoringThread

    # print "client connected"
    app.logger.info("client connected")

    if not alarmStateThread.isAlive():
        print "Starting alarmStateThread"
        app.logger.info("Starting alarmStateThread")
        alarmStateThread = threading.Thread(name='alarmstate_process_thread_',target= alarm_state, args=())
        alarmStateThread.start()
   
    if not facesUpdateThread.isAlive():
        print "Starting facesUpdateThread"
        app.logger.info("Starting facesUpdateThread")
        facesUpdateThread = threading.Thread(name='websocket_process_thread_',target= update_faces, args=())
        facesUpdateThread.start()

    if not facesDetectingThread.isAlive():
        print "Starting facesDetectingThread"
        app.logger.info("Starting facesDetectingThread")
        facesDetectingThread = threading.Thread(name='websocket_process_thread_',target= detecting_faces, args=())
        facesDetectingThread.start()

    if not monitoringThread.isAlive():
        print "Starting monitoringThread"
        app.logger.info("Starting monitoringThread")
        monitoringThread = threading.Thread(name='monitoring_process_thread_',target= system_monitoring, args=())
        monitoringThread.start()

    cameraData = {}
    cameras = []

    with HomeSurveillance.camerasLock :
        for i, camera in enumerate(HomeSurveillance.cameras):
            with HomeSurveillance.cameras[i].peopleDictLock:
                cameraData = {'camNum': i , 'url': camera.url}
                # print cameraData
                app.logger.info(cameraData)
                cameras.append(cameraData)
    alertData = {}
    alerts = []
    for i, alert in enumerate(HomeSurveillance.alerts):
        with HomeSurveillance.alertsLock:
            alertData = {'alert_id': alert.id , 'alert_message':  "Alert if " + alert.alertString}
            # print alertData
            app.logger.info(alertData)
            alerts.append(alertData)
   
    systemData = {'camNum': len(HomeSurveillance.cameras) , 'people': HomeSurveillance.peopleDB, 'cameras': cameras, 'alerts': alerts, 'onConnect': True}
    socketio.emit('system_data', json.dumps(systemData) ,namespace='/surveillance')

@socketio.on('disconnect', namespace='/surveillance')
def disconnect():
    # print('Client disconnected')
    app.logger.info("Client disconnected")


if __name__ == '__main__':

     # Starts server on default port 5000 and makes socket connection available to other hosts (host = '0.0.0.0')
     formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
     handler = RotatingFileHandler(LOG_FILE, maxBytes=1000000, backupCount=10)
     handler.setLevel(logging.DEBUG)
     handler.setFormatter(formatter)
     app.logger.addHandler(handler)
     app.logger.setLevel(logging.DEBUG)

     log = logging.getLogger('werkzeug')
     log.setLevel(logging.DEBUG)
     log.addHandler(handler)
     socketio.run(app, host='0.0.0.0', debug=False, use_reloader=False)
