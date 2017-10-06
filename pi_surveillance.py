#import the necessary packages
from pyimagesearch.tempimage import TempImage
from picamera.array import PiRGBArray
from picamera import PiCamera
import dropbox
import argparse
import warnings
import datetime
import imutils
import shutil
import json
import time
import cv2
import os
import datetime as dt
import scrape_sun

#construct the argument parser and parse the arguments
ap = argparse.ArgumentParser()
ap.add_argument("-c", "--conf", required=True, help="path to the JSON config file")
args = vars(ap.parse_args())

#filter warnings, load the config and initialize the Dropbox Client
warnings.filterwarnings("ignore")
conf = json.load(open(args["conf"]))
client = None

if conf["use_dropbox"]:
  #connect to dropbox and start the session authorization process
  accessToken = conf["access_token"]
  client = dropbox.Dropbox(accessToken)
  print "[SUCCESS] dropbox account linked"

#initialize the camera and grab a reference to the raw camera capture
camera = PiCamera()
camera.resolution = tuple(conf["resolution"])
camera.framerate = conf["fps"]
rawCapture = PiRGBArray(camera, size=tuple(conf["resolution"]))

#allow the camera to warmup, then initialize the average frame, last
#uploaded timestamp, and frame motion counter
print "[INFO] warming up..."
time.sleep(conf["camera_warmup_time"])
avg = None
lastUploaded = datetime.datetime.now()
motionCounter = 0

#capture frames from the camera
for f in camera.capture_continuous(rawCapture, format="bgr", use_video_port=True):
  #Only start video capture if 
  now = dt.datetime.now()
  url = "https://www.timeanddate.com/sun/usa/salt-lake-city"
  sunrise, sunset = scrape_sun.get_times(url, 'span', 'three', now)
  if now < sunrise or now > sunset:
    continue

  #grab the raw Numpy array representing the image and initialize
  #the timestamp and occupied/unoccupied text
  frame = f.array
  timestamp = datetime.datetime.now()
  text = "Unoccupied"

  #resize the frame, convert it to grayscale and blur it
  frame = imutils.resize(frame, width=500)
  gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
  gray = cv2.GaussianBlur(gray, (21,21),0)

  #if the average frame is None, initialize it
  if avg is None:
    print "[INFO] starting background model..."
    avg = gray.copy().astype("float")
    rawCapture.truncate(0)
    continue

  #accumulate the weighted average between the current frame and
  #previous frames, then compute the difference between the current
  #frame and running average
  cv2.accumulateWeighted(gray, avg, 0.5)
  frameDelta = cv2.absdiff(gray, cv2.convertScaleAbs(avg))

  #theshold the delta image, dilate the theshold image to fill
  #in holes, then find contours on threshold image
  thresh = cv2.threshold(frameDelta, conf["delta_thresh"], 255, cv2.THRESH_BINARY)[1]
  thresh = cv2.dilate(thresh, None, iterations=2)
  cnts = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
  cnts = cnts[0] if imutils.is_cv2() else cnts[1]

  #loop over the contours
  for c in cnts:
    #if the contour is too small, ignore it
    if cv2.contourArea(c) < conf["min_area"]:
      continue
    
    #compute the bounding box for the contour, draw it on the frame, and update the text
    (x,y,w,h) = cv2.boundingRect(c)
    cv2.rectangle(frame,(x,y), (x+w, y+h), (0,255,0),2)
    text = "Occupied"

  #draw the text and timestamp
  ts = timestamp.strftime("%A %d %B %Y %I:%M:%S%p")
  cv2.putText(frame, "Room Status: {}".format(text), (10,20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,255),2)
  cv2.putText(frame, ts, (10, frame.shape[0]-10), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0,0,255),1)

  #check to see if room is occupied
  if text == "Occupied":
    #check to see if enough time has passed between uploads
    if (timestamp - lastUploaded).seconds >= conf["min_upload_seconds"]:
      #increment the motion counter
      motionCounter += 1

      #check to see if the number of frames with consistent motion is high enough
      if motionCounter >= conf["min_motion_frames"]:

        #check to see if dropbox should be used
        if conf["use_dropbox"]:
          #write the image to temporary file
          t = TempImage()
          cv2.imwrite(t.path, frame)

          #upload the image to Dropbox and cleanup the temp image
          print("[UPLOAD] {}".format(ts))
          path = "/{base_path}/{timestamp}.jpg".format(
              base_path=conf["dropbox_base_path"], timestamp=ts)
          mode = dropbox.files.WriteMode.add
          with open(t.path, 'rb') as f:
              data = f.read()
          try:
             res = client.files_upload(
                data, path, mode, mute=True)
          except dropbox.exceptions.ApiError as err:
                print('*** API error', err)
            
          #Send image to email address
          if conf["use_email"]:
              body = open("body.txt", "w+")
              body.write("UPLOAD {}".format(ts))
              body.close          
              os.system(
		"mpack -s 'Surveillance' -d {body} {path} {email}".format(
		body="./body.txt", path=t.path, email=conf["email"]))

          #Save image to usbdrive
          usbpath = '/mnt/usbdrive/photos'
          dtnow = datetime.datetime.now()
          if dtnow.hour >= 12:
            ampm = "PM"
          else:
            ampm = "AM"
          new_image_path = os.path.join(usbpath, ampm, ts + '.jpg')
          shutil.copy2(t.path, new_image_path)

          t.cleanup()

        #update the last uploaded timestamp and reset he motion couner
        lastUploaded = timestamp
        motionCounter = 0

  #otherwise the room is not occupied
  else:
    motionCounter = 0

  #check to see if the frames should be displayed to screen
  if conf["show_video"]:
    #display the security feed
    cv2.imshow("Security Feed", frame)
    key = cv2.waitKey(1) & 0xFF

    #if the 'q' key is pressed, break from loop
    if key == ord('q'):
      break

  #clear the stream in preparation for the next frame
  rawCapture.truncate(0)


  
