#!/usr/bin/env python2

from pypylon import pylon
from pypylon import genicam
from serial import Serial

import array
import sys
import errno
import os
import optparse
import hashlib
import cv2 #from scipy.misc import imsave
import threading
import time
from datetime import datetime

from queue import Queue
import numpy as np
import multiprocessing as mp

from samples.configurationeventprinter import ConfigurationEventPrinter
from samples.imageeventprinter import ImageEventPrinter

current_ms_time = lambda: int(round(time.time() * 1000))


def extract_options(options):

    parser = optparse.OptionParser()
    parser.add_option('--output-path', action="store", dest="output_path", default="/home/labuser/Documents/video_data", help="out path directory [default: /home/labuser/Documents/video_data]")
    parser.add_option('--output-format', action="store", dest="output_format", type="choice", choices=['png', 'npz'], default='png', help="out file format, png or npz [default: png]")
    parser.add_option('--save', action='store_true', dest='save_images', default=False, help='Flag to save images to disk.')
    parser.add_option('--basename', action="store", dest="basename", default="default_frame", help="basename for saved files")

    parser.add_option('--write-process', action="store_true", dest="save_in_separate_process", default=True, help="spawn process for disk-writer [default: True]")
    parser.add_option('--write-thread', action="store_false", dest="save_in_separate_process", help="spawn threads for disk-writer")
    parser.add_option('--frame-rate', action="store", dest="frame_rate", help="requested frame rate", type="float", default=60.0)
    parser.add_option('--port', action="store", dest="port", help="port for arduino (default: /dev/ttyUSB0)", default='/dev/ttyUSB0')
    parser.add_option('--disable', action='store_false', dest='enable_framerate', default=True, help='Flag to disable acquisition frame rate setting.')


    (options, args) = parser.parse_args()

    return options




def connect_to_camera(connect_retries=50, frame_rate=20., acquisition_line='Line3', enable_framerate=True):
    print('Searching for camera...')

    camera = None
    # get the camera list 
    print('Connecting to camera...')   
    n = 0
    while camera is None and n < connect_retries:
        try:
            camera = pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateFirstDevice())
            print(camera)
            #time.sleep(0.5)
            #camera.Open()
            #print("Bound to device:" % (camera.GetDeviceInfo().GetModelName()))

        except Exception as e:
            print('.')
            time.sleep(0.1)
            camera = None
            n += 1

    if camera is None:
        try:
            import opencv_fallback

            camera = opencv_fallback.Camera(0)

            print("Bound to OpenCV fallback camera.")
        except Exception as e2:
            print("Could not load OpenCV fallback camera")
            print(e2)
            exit()
    else:
        camera.Open()
        print("Bound to device: %s" % (camera.GetDeviceInfo().GetModelName()))

    camera.AcquisitionFrameRateEnable = enable_framerate
    camera.AcquisitionFrameRate = frame_rate
    if enable_framerate:
        camera.AcquisitionMode.SetValue('Continuous')
        print("Set acquisition frame rate: %.2f Hz" % camera.AcquisitionFrameRate())
        for trigger_type in ['FrameStart', 'FrameBurstStart']:
            camera.TriggerSelector = trigger_type
            camera.TriggerMode = "Off"
    else: 
        # Set  trigger
        camera.TriggerSelector = "FrameStart"
        camera.TriggerMode = "On"
    
    camera.TriggerSource.SetValue(acquisition_line)
    #camera.TriggerSelector.SetValue('AcquisitionStart')
    camera.TriggerActivation = 'RisingEdge'

    # Set IO lines:
    camera.LineSelector.SetValue(acquisition_line) # select GPIO 1
    camera.LineMode.SetValue('Input')     # Set as input
    #camera.LineStatus.SetValue(False)
    # Output:
    camera.LineSelector.SetValue('Line4')
    camera.LineMode.SetValue('Output')
    camera.LineSource.SetValue('UserOutput3') # Set source signal to User Output 1
    camera.UserOutputSelector.SetValue('UserOutput3')
    camera.UserOutputValue.SetValue(False)
      
        
 
    # Set image format:
    camera.Width.SetValue(960)
    camera.Height.SetValue(600)
    camera.BinningHorizontalMode.SetValue('Sum')
    camera.BinningHorizontal.SetValue(2)
    camera.BinningVerticalMode.SetValue('Sum')
    camera.BinningVertical.SetValue(2)
    camera.PixelFormat.SetValue('Mono8')

    camera.ExposureMode.SetValue('Timed')
    camera.ExposureTime.SetValue(40000)


    try:
        actual_framerate = camera.ResultingFrameRate.GetValue()
        assert camera.AcquisitionFrameRate() <= camera.ResultingFrameRate(), "Unable to acquieve desired frame rate (%.2f Hz)" % float(camera.AcquisitionFrameRate.GetValue())
    except AssertionError:
        camera.AcquisitionFrameRate.SetValue(float(camera.ResultingFrameRate.GetValue()))
        print("Set acquisition rate to: %.2f" % camera.AcquisitionFrameRate())


    return camera


# compute a hash from the current time so that we don't accidentally overwrite old data
#run_hash = hashlib.md5(str(time.time())).hexdigest()

# ############################################
# Camera functions
# ############################################

class SampleImageEventHandler(pylon.ImageEventHandler):
    def OnImageGrabbed(self, camera, grabResult):
        #print("CSampleImageEventHandler::OnImageGrabbed called.")
        camera.UserOutputValue.SetValue(True)
        #camera.UserOutputValue.SetValue(True)
        
if __name__ == '__main__':

    optsE = extract_options(sys.argv[1:])
    acquire_images = True
    save_images = optsE.save_images #True

    output_path = optsE.output_path
    output_format = optsE.output_format
    save_in_separate_process = optsE.save_in_separate_process   
    save_as_png = optsE.output_format=='png'
    basename = optsE.basename

    # Camera settings:
    frame_rate = optsE.frame_rate

    # Make the output path if it doesn't already exist
    output_dir = os.path.join(output_path, basename)
    frame_write_dir = os.path.join(output_dir, 'frames')
    try:
        os.makedirs(frame_write_dir)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise e
        pass

             
    cv2.namedWindow('cam_window')
    r = np.random.rand(100,100)
    cv2.imshow('cam_window', r)

    time.sleep(1.0)

    # -------------------------------------------------------------
    # Camera Setup
    # ------------------------------------------------------------     
    enable_framerate = optsE.enable_framerate
    acquisition_line = 'Line3'
    camera = None
    if acquire_images:
        camera = connect_to_camera(frame_rate=frame_rate, acquisition_line=acquisition_line, enable_framerate=enable_framerate)
           
    # Attach event handlers:
    camera.RegisterImageEventHandler(SampleImageEventHandler(), pylon.RegistrationMode_Append, pylon.Cleanup_Delete)

    time.sleep(1)
    print("Camera ready!")

    # -------------------------------------------------------------
    # Set up a thread to write stuff to disk
    # -------------------------------------------------------------
    if save_in_separate_process:
        im_queue = mp.Queue()
    else:
        im_queue = Queue()

    def save_images_to_disk():
        print('Disk-saving thread active...')

        # Create frame metadata file:
        date_fmt = '%Y%m%d_%H%M%S%f'
        tstamp = datetime.now().strftime(date_fmt)
        
        serial_outfile = os.path.join(output_dir, '%s_frame_metadata_%s.txt' % (basename, tstamp))
        print("Created outfile: %s" % serial_outfile)
        serial_file = open(serial_outfile, 'w+')
        serial_file.write('frame\tframe_ID\tframe_tstamp\tacq_trigger\tframe_trigger\trelative_time\trelative_camera_time\n')

        n = 0
        result = im_queue.get()
        while result is not None: 
            (im_array, metadata) = result
            if n==0:
                start_time = time.clock() 
                cam_start_time = metadata['tstamp']

            name = '%i_%i_%i' % (n, metadata['ID'], metadata['tstamp'])
            if save_as_png:
                fpath = os.path.join(frame_write_dir, '%s.png' % name)
                cv2.imwrite(fpath, im_array)
            else:
                fpath = os.path.join(frame_write_dir, '%s.npz' % name)
                np.savez_compressed(fpath, im_array)

            serial_file.write('\t'.join([str(s) for s in [n, metadata['ID'], metadata['tstamp'], metadata['acq_trigger'], metadata['frame_trigger'], str(time.clock()-start_time), (metadata['tstamp']-cam_start_time)/1E9]]) + '\n')
            n += 1
            result = im_queue.get()

        disk_writer_alive = False 
        print('Disk-saving thread inactive...')
        serial_file.flush()
        serial_file.close()
        print("Closed data file...")

    if save_in_separate_process:
        disk_writer = mp.Process(target=save_images_to_disk)
    else:
        disk_writer = threading.Thread(target=save_images_to_disk)

    if save_images:
        disk_writer.daemon = True
        disk_writer.start()

    nframes = 0
    t = 0
    last_t = None

    report_period = 60 # frames
    timeout_time = 1000


    camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly) #GrabStrategy_OneByOne)
    # converting to opencv bgr format  
    converter = pylon.ImageFormatConverter()
    converter.OutputPixelFormat = pylon.PixelType_BGR8packed
    converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned
    
    camera.LineSelector.SetValue(acquisition_line) 
    sync_line = camera.LineSelector.GetValue()
    sync_state = camera.LineStatus.GetValue()
    print("Waiting for Acquisition Start trigger...", sync_state)
    while sync_state is False: 
        #print("[%s] trigger" % sync_line, sync_state)
        sync_state = camera.LineStatus.GetValue()

    print("... ... MW trigger received!")
    camera.AcquisitionStart.Execute()

    #while True:
        #camera.WaitForFrameTriggerReady(100)

    # Start acquiring
    print('Beginning imaging [Hit ESC to quit]...')
    while camera.IsGrabbing():
        t = time.time()
                
        #while camera.IsGrabbing():
        # Grab a frame:
        #camera.WaitForFrameTriggerReady(100)
        res = camera.RetrieveResult(timeout_time, pylon.TimeoutHandling_ThrowException)
        if res.GrabSucceeded():
            # Access img data:
            im_native = res.Array
            im_to_show = converter.Convert(res)
            im_array = im_to_show.GetArray()
            frame_state = camera.UserOutputValue.GetValue()
            meta = {'tstamp': res.TimeStamp, 
                    'ID': res.ID,
                    'number': res.ImageNumber,
                    'acq_trigger': sync_state,
                    'frame_trigger': frame_state}
            if save_images:
                im_queue.put((im_native, meta))
            nframes += 1

        # Show image:
        cv2.imshow('cam_window', im_array)
        camera.UserOutputValue.SetValue(False)

        # Break out of the while loop if ESC registered
        key = cv2.waitKey(1)
        sync_state = camera.LineStatus.GetValue()
        if key == 27 or sync_state is False: # ESC
            break
        res.Release()

        if nframes % report_period == 0:
            if last_t is not None:
                print('avg frame rate: %f [Hit ESC to quit]' % (report_period / (t - last_t)))
                print('ID: %i, nframes: %i, %s' % (meta['ID'], nframes, meta['tstamp']) )
            last_t = t

    camera.AcquisitionStop.Execute()
    #camera.AcquisitionStart.Execute()

    # Relase the resource:
    camera.UserOutputValue.SetValue(False) 
    camera.StopGrabbing()
    cv2.destroyAllWindows()

    camera.Close() 


    if im_queue is not None:
        im_queue.put(None)

    if save_images:
        hang_time = time.time()
        nag_time = 0.05

        sys.stdout.write('Waiting for disk writer to catch up (this may take a while)...')
        sys.stdout.flush()
        waits = 0
        while not im_queue.empty():
            now = time.time()
            if (now - hang_time) > nag_time:
                sys.stdout.write('.')
                sys.stdout.flush()
                hang_time = now
                waits += 1

        print(waits)
        print("\n")

        if not im_queue.empty():
            print("WARNING: not all images have been saved to disk!")

        disk_writer_alive = False

        if save_in_separate_process and disk_writer is not None:
            print("Terminating disk writer...")
            disk_writer.join()
            # disk_writer.terminate()
        
        # disk_writer.join()
        print('Disk writer terminated')        
        
        #ser.write('F'.encode())


        #serial_file.flush()
        #serial_file.close()
        #print("Closed serial file.")

