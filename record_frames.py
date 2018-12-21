#!/usr/bin/env python2

from pypylon import pylon
from pypylon import genicam

import sys
import errno
import os
import optparse
import hashlib
import cv2 #from scipy.misc import imsave
import threading
import time

from queue import Queue
import numpy as np
import multiprocessing as mp

from samples.configurationeventprinter import ConfigurationEventPrinter
from samples.imageeventprinter import ImageEventPrinter

current_ms_time = lambda: int(round(time.time() * 1000))

def getkey():
    return input("Enter \"s\" to trigger the camera or \"q\" to exit and press enter? (s/q) ")


def extract_options(options):

    parser = optparse.OptionParser()
    parser.add_option('--output-path', action="store", dest="output_path", default="/tmp/frames", help="out path directory [default: /tmp/frames]")
    parser.add_option('--output-format', action="store", dest="output_format", type="choice", choices=['png', 'npz'], default='png', help="out file format, png or npz [default: png]")
    parser.add_option('--save', action='store_true', dest='save_images', default=False, help='Flag to save images to disk.')

    parser.add_option('--write-process', action="store_true", dest="save_in_separate_process", default=True, help="spawn process for disk-writer [default: True]")
    parser.add_option('--write-thread', action="store_false", dest="save_in_separate_process", help="spawn threads for disk-writer")
    parser.add_option('--frame-rate', action="store", dest="frame_rate", help="requested frame rate", type="float", default=60.0)
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
    frame_rate = optsE.frame_rate

    save_as_png = optsE.output_format=='png'

    # Make the output path if it doesn't already exist
    try:
        os.makedirs(output_path)
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

    disk_writer_alive = True

    def save_images_to_disk():
        print('Disk-saving thread active...')
        n = 0
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

                # print name
                name = '%i_%i_%i' % (n, metadata['ID'], metadata['tstamp'])
                if save_as_png:
                    fpath = os.path.join(output_path, '%s.png' % name)
                    cv2.imwrite(fpath, im_array)
                else:
                    fpath = os.path.join(output_path, '%s.npz' % name)
                    np.savez_compressed(fpath, im_array)
                n += 1
        print('Disk-saving thread inactive...')

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

    while True:
        user_key = getkey()
        if user_key == 's':
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
                    meta = {'tstamp': res.TimeStamp, 
                            'ID': res.ID,
                            'number': res.ImageNumber}

                nframes += 1
                if save_images:
                    im_queue.put((im_native, meta))

                # Show image:
                cv2.imshow('cam_window', im_array)
                
                # Break out of the while loop if these keys are registered
                key = cv2.waitKey(1)
                if key == 27: # ESC
                    break
                res.Release()

                if nframes % report_period == 0:
                    if last_t is not None:
                        print('avg frame rate: %f [Hit ESC to quit]' % (report_period / (t - last_t)))
                        print('ID: %i, nframes: %i' % (meta['ID'], nframes) )
                    last_t = t

            # Relase the resource:
            camera.StopGrabbing()
            cv2.destroyAllWindows()

            camera.Close() 

        elif user_key == 'q':
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

