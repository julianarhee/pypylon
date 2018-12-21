'''
A simple Program for grabing video from basler camera and converting it to opencv img.
Tested on Basler acA1300-200uc (USB3, linux 64bit , python 3.5)

'''
from pypylon import pylon
from pypylon import genicam

import sys
import os
import cv2
import optparse
import datetime

from configurationeventprinter import ConfigurationEventPrinter
from imageeventprinter import ImageEventPrinter

import time

current_ms_time = lambda: int(round(time.time() * 1000))


def extract_options(options):
    parser = optparse.OptionParser()
    parser.add_option('--save', action='store_true', dest='save_images', default=False, help='add flag to save images to disk')
    parser.add_option('-D', '--output-dir', action='store', dest='base_dir', default='/tmp/basler_data', help='output base dir for saving images')
    (options, args) = parser.parse_args()

    return options



def getkey():
    return input("Enter \"s\" to trigger the camera or \"q\" to exit and press enter? (s/q) ")

# Example of an image event handler.
class SampleImageEventHandler(pylon.ImageEventHandler):

   def OnImageGrabbed(self, camera, grabResult):
        print("CSampleImageEventHandler::OnImageGrabbed called.")
        print('grabbed image!')

def save_image(output_dir, img):
    img_output =  os.path.join(output_dir, '%i.png' % img_counter)
    cv2.imwrite(img_outpath, img)


if __name__ == '__main__':
    try:


        optsE = extract_options(sys.argv[1:])
        save_images = optsE.save_images
        base_dir = optsE.base_dir
        if save_images:
            datestr = datetime.datetime.now().strftime("%Y%m%d_%H%M_%S")
            output_dir = '%s_%s' % (base_dir, datestr) 
            if not os.path.exists(output_dir): os.makedirs(output_dir)
            print("Output saved to:\n%s" % output_dir)

        # Create an instant camera object for the camera device found first.
        camera = pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateFirstDevice())
        #camera.save_images = save_images

        # Register the standard configuration event handler for enabling software triggering.
        # The software trigger configuration handler replaces the default configuration
        # as all currently registered configuration handlers are removed by setting the registration mode to RegistrationMode_ReplaceAll.
#        camera.RegisterConfiguration(pylon.SoftwareTriggerConfiguration(), pylon.RegistrationMode_ReplaceAll,
#                                     pylon.Cleanup_Delete)
#
        # For demonstration purposes only, add a sample configuration event handler to print out information
        # about camera use.t
        #camera.RegisterConfiguration(ConfigurationEventPrinter(), pylon.RegistrationMode_Append, pylon.Cleanup_Delete)

        # The image event printer serves as sample image processing.
        # When using the grab loop thread provided by the Instant Camera object, an image event handler processing the grab
        # results must be created and registered.
        #camera.RegisterImageEventHandler(ImageEventPrinter(), pylon.RegistrationMode_Append, pylon.Cleanup_Delete)

        # For demonstration purposes only, register another image event handler.
        camera.RegisterImageEventHandler(SampleImageEventHandler(), pylon.RegistrationMode_Append, pylon.Cleanup_Delete)

        # Start the grabbing using the grab loop thread, by setting the grabLoopType parameter
        # to GrabLoop_ProvidedByInstantCamera. The grab results are delivered to the image event handlers.
        # The GrabStrategy_OneByOne default grab strategy is used.
        #camera.StartGrabbing(pylon.GrabStrategy_OneByOne, pylon.GrabLoop_ProvidedByInstantCamera)

        while True:
            user_key = getkey() #cv2.waitKey(1)
            if user_key == 's':
         
                # Grabing Continusely (video) with minimal delay
                camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly) 
                converter = pylon.ImageFormatConverter()

                # converting to opencv bgr format
                converter.OutputPixelFormat = pylon.PixelType_BGR8packed
                converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned
                img_counter = 0

                while camera.IsGrabbing():
                    grabResult = camera.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)

                    if grabResult.GrabSucceeded():
                        # Access the image data
                        image = converter.Convert(grabResult)
                        img = image.GetArray()
                        cv2.namedWindow('title', cv2.WINDOW_NORMAL)
                        cv2.imshow('title', img)

                        if save_images:
                            tstamp = current_ms_time()
                            img_fpath = os.path.join(output_dir, '%i_%i.png' % (img_counter, tstamp))
                            cv2.imwrite(img_fpath, img)

                            img_counter += 1
                        k = cv2.waitKey(1)
                        if k == 27:
                            break
                    grabResult.Release()
                    
                # Releasing the resource    
                camera.StopGrabbing()

                cv2.destroyAllWindows()
               
            elif user_key == 'q':
                break
           
    except genicam.GenericException as e:
        # Error handling.
        print("An exception occurred.", e.GetDescription())
