#!/usr/bin/env python2

from pypylon import pylon
from pypylon import genicam
from serial import Serial

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

def getkey():
    return input("Enter \"s\" to trigger the camera or \"q\" to exit and press enter? (s/q) ")

def flushBuffer():
    #Flush out serial buffer
    global ser
#    ser.flushInput()
#    ser.flushOutput()
    tmp=0;
    while tmp is not b'':
        print('.. flushing ...')
        tmp=ser.read()

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


    (options, args) = parser.parse_args()

    return options




def connect_to_camera(connect_retries=50, frame_rate=None):
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

    if frame_rate is not None:
        camera.AcquisitionFrameRateEnable = True
        camera.AcquisitionFrameRate = frame_rate
        print("Set acquisition frame rate: %.2f Hz" % camera.AcquisitionFrameRate())

    return camera


# compute a hash from the current time so that we don't accidentally overwrite old data
#run_hash = hashlib.md5(str(time.time())).hexdigest()


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
    # -------------------------------------------------------------
    if acquire_images:
        camera = connect_to_camera(frame_rate=frame_rate)

    # -------------------------------------------------------------
    # Set up a thread to write stuff to disk
    # -------------------------------------------------------------
    if save_in_separate_process:
        im_queue = mp.Queue()
    else:
        im_queue = Queue()


    # Create frame metadata file:
    date_fmt = '%Y%m%d_%H%M%S%f'
    tstamp = datetime.now().strftime(date_fmt)
    if save_images: 
        serial_outfile = os.path.join(output_dir, '%s_frame_metadata_%s.txt' % (basename, tstamp))
        print("Creating outfile: %s" % serial_outfile)
        #serial_file = open(serial_outfile, 'w')
        #serial_file.write('frame\tframe_ID\tframe_tstamp\tacq_trigger\tstim_trigger\trelative_time\n')


    # Start Arduino
    port = optsE.port
    baudrate = 115200
    ser = Serial(port, baudrate, timeout=0.5)
    print("Connecting to serial port - %s - baudrate %i" % (port,  baudrate))
    time.sleep(1)
    flushBuffer()
    print('... flushed...')
    sys.stdout.flush()
    print("Connected serial port.")


    ser.write('S'.encode())
    print("-- triggered Arduino.")
    print("Waiting for experiment start.")

    time.sleep(1)
    while 1:
        first_byte = ser.read(1)
        print(first_byte)
        if first_byte is not b'':
            disk_writer_alive = True            
            session_start_time = time.clock()
            start_key = 's'
            second_byte = ser.read(1)
            print(second_byte)
            break 
    print("... ... MW trigger received!")

    def save_images_to_disk(serial_outfile):
        print('Disk-saving thread active...')
        n = 0
        serial_file = open(serial_outfile, 'w+')
        print("Created outfile: %s" % serial_outfile)
        serial_file.write('frame\tframe_ID\tframe_tstamp\tacq_trigger\tstim_trigger\trelative_time\n')


        while disk_writer_alive: 
            if not im_queue.empty():            
                try:
                    result = im_queue.get()
                    if result is None:
                        break
                    # unpack
                    (im_array, metadata) = result
                except e as Exception:
                    break
                
                if n == 0:
                    start_time = time.clock()
                    print("Acquisition started!")
                # print name
                name = '%i_%i_%i' % (n, metadata['ID'], metadata['tstamp'])
                if save_as_png:
                    fpath = os.path.join(frame_write_dir, '%s.png' % name)
                    cv2.imwrite(fpath, im_array)
                else:
                    fpath = os.path.join(frame_write_dir, '%s.npz' % name)
                    np.savez_compressed(fpath, im_array)

                serial_file.write('\t'.join([str(s) for s in [n, metadata['ID'], metadata['tstamp'], metadata['acq_trigger'], metadata['stim_trigger'], str(time.clock()-start_time)]]) + '\n')
                serial_file.flush()
                #serial_file.write('%i\t%i\t%i\t%i\t%i\t%i\n' % (n, metadata['ID'], int(metadata['tstamp']), metadata['acq_trigger'], metadata['stim_trigger'], time.clock() - start_time))
                n += 1
        serial_file.flush()
        serial_file.close()
        print('Disk-saving thread inactive...')

    if save_in_separate_process:
        disk_writer = mp.Process(target=save_images_to_disk, args=(serial_outfile,))
    else:
        disk_writer = threading.Thread(target=save_images_to_disk, args=(serial_outfile,))

    if save_images:
        disk_writer.daemon = True
        disk_writer.start()

    nframes = 0
    t = 0
    last_t = None

    report_period = 60 # frames
    timeout_time = 1000

    while True:
        user_key = getkey()
        if start_key == 's':
            # Start acquiring
            camera.StartGrabbing(pylon.GrabStrategy_OneByOne)
            converter = pylon.ImageFormatConverter()
            # converting to opencv bgr format
            converter.OutputPixelFormat = pylon.PixelType_BGR8packed
            converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned
            print('Beginning imaging [Hit ESC to quit]...')
         
            while camera.IsGrabbing():
                t = time.time()

                # Grab a frame:
                res = camera.RetrieveResult(timeout_time, pylon.TimeoutHandling_ThrowException)
                if res.GrabSucceeded():
                    # Access img data:
                    im_native = res.Array
                    im_to_show = converter.Convert(res)
                    im_array = im_to_show.GetArray()

                    # Get IO sync events:
                    read_byte = ser.read(1)
                    acq_trigger = ord(read_byte)
                    read_byte2 = ser.read(1)
                    stim_trigger = ord(read_byte2) 
                    print(read_byte, read_byte2)
                    #print("acq: %i, stim: %i" % (acq_trigger, stim_trigger))

                    meta = {'tstamp': res.TimeStamp, 
                            'ID': res.ID,
                            'number': res.ImageNumber,
                            'acq_trigger': acq_trigger,
                            'stim_trigger': stim_trigger}

                nframes += 1
                if save_images:
                    im_queue.put((im_native, meta))

                # Show image:
                cv2.imshow('cam_window', im_array)
                
                # Break out of the while loop if these keys are registered
                key = cv2.waitKey(1)
                if key == 27: # ESC
                    start_key='q'
                    break
                res.Release()

                if nframes % report_period == 0:
                    if last_t is not None:
                        print('avg frame rate: %f [Hit ESC to quit]' % (report_period / (t - last_t)))
                        print('ID: %i, nframes: %i, %s' % (meta['ID'], nframes, meta['tstamp']) )
                    last_t = t

            # Relase the resource:
            camera.StopGrabbing()
            cv2.destroyAllWindows()

            camera.Close() 

        elif user_key == 'q':
            start_key='q'
            break

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
        
        ser.write('F'.encode())


        #serial_file.flush()
        #serial_file.close()
        #print("Closed serial file.")

