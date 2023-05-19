# -*- coding: utf-8 -*-

from __future__ import print_function
import os
import cv2
from models import *
import torch
import numpy as np
import time
from config import Config
from torch.nn import DataParallel
import dlib
import piheaan as heaan
from heaan_utils import Heaan
import pandas as pd


class FeatureProcessing:
    def __init__(self) -> None:
        self.face_detector = dlib.get_frontal_face_detector()

    def get_features(self, model, frame, device):
        pre_res = self.preproc(frame)
        if type(pre_res) != int:
            data = torch.from_numpy(pre_res)
            data = data.to(device)
            feat = model(data)
            feat = feat.detach().numpy()
            fe_1 = feat[::2]
            fe_2 = feat[1::2]
            feature = np.hstack((fe_1, fe_2))
            return feature
        else:
            if pre_res == 0:    return 0 # No face
            else:   return -1 # Many face

    def preproc(self, frame):
        dets = self.face_detector(frame, 0)
        img_dir_path = 'face_image/face_images'
        # when face not detected
        if len(dets) == 0:
            # return 0
            face = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            face = cv2.resize(face, (125, 125), interpolation=cv2.INTER_CUBIC)
            faces = np.dstack((face, np.fliplr(face))).transpose((2, 0, 1))
            faces = faces[:, np.newaxis, :, :]
            faces = faces.astype(np.float32, copy=False)
            faces -= 127.5
            faces /= 127.5
            return faces
        # when face detected
        elif len(dets) == 1:
            d = dets[0]
            face = frame[d.top():d.bottom(), d.left():d.right()] # face 차원 확인하기
            face = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
            face = cv2.resize(face, (125, 125), interpolation=cv2.INTER_CUBIC)
            # generating image path
            img_path = os.path.join(img_dir_path, "{}.jpg".format(time.time()))
            # storing image when pressing space keyboard
            if cv2.waitKey(1) == 32:
                cv2.imwrite(img_path, face)
                
            cv2.imwrite('tmp.jpg', face)
            faces = np.dstack((face, np.fliplr(face))).transpose((2, 0, 1))
            faces = faces[:, np.newaxis, :, :]
            faces = faces.astype(np.float32, copy=False)
            faces -= 127.5
            faces /= 127.5
            return faces
        else:
            return -1


if __name__ == '__main__':

    # log_slots is used for the number of slots per ciphertext
    # It depends on the parameter used (ParameterPreset)
    # The number '15' is the value for maximum number of slots,
    # but you can also use a smaller number (ex. 2, 3, 5, 7 ...)
    # The actual number of slots in the ciphertext is calculated as below.
    he = Heaan()
    ctxt1, ctxt2 = he.heaan_initilize()

    opt = Config()
    if opt.backbone == 'resnet18':
        model = resnet_face18(opt.use_se)
    elif opt.backbone == 'resnet34':
        model = resnet34()
    elif opt.backbone == 'resnet50':
        model = resnet50()

    cpu = torch.device("cpu")
    model = DataParallel(model)
    model.load_state_dict(torch.load(opt.test_model_path, map_location=torch.device('cpu')))
    model.to(cpu)
    model.eval()

    fe_proc = FeatureProcessing()
    
    avg_dir_path = 'face_image/average_image'
    img_dir_path = 'face_image/face_images'

    register_feat = np.array([])
    avg_feat = None
    
    webcam = cv2.VideoCapture(0)
    if not webcam.isOpened():
        print("Could not open webcam")
        exit()

    while webcam.isOpened():
        status, frame = webcam.read()
        if status:
            feature = fe_proc.get_features(model, frame, cpu)

            # User registeration part
            if register_feat.shape[0] <= 5: 
                if isinstance(feature, np.ndarray):
                    if register_feat.size == 0:
                        register_feat = feature
                    else:
                        register_feat = np.concatenate([register_feat, feature]) # stack
                
                    if register_feat.shape[0] == 0:
                        frame = cv2.putText(frame, "User Registration Start!", (350, 40), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 3, cv2.LINE_AA)
                        frame = cv2.putText(frame, "Look front!", (350, 80), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 3, cv2.LINE_AA)
                    elif register_feat.shape[0] == 1:
                        frame = cv2.putText(frame, "Head up!", (350, 80), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 3, cv2.LINE_AA)
                    elif register_feat.shape[0] == 2:
                        frame = cv2.putText(frame, "Eyes on left!", (350, 80), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 3, cv2.LINE_AA)
                    elif register_feat.shape[0] == 3:
                        frame = cv2.putText(frame, "Eyes on right!", (350, 80), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 3, cv2.LINE_AA)
                    elif register_feat.shape[0] == 4:
                        frame = cv2.putText(frame, "Look front again!", (350, 80), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 3, cv2.LINE_AA)
                    elif register_feat.shape[0] == 5:
                        frame = cv2.putText(frame, "User Registration Finish!", (350, 80), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 3, cv2.LINE_AA)

                        # avg : average featue
                        avg_feat = np.mean(register_feat, axis=0)
                        msg1 = he.feat_msg_generate(avg_feat)
                        he.encrypt(msg1, ctxt1)
                        # ctxt1.save('face_image/average_ctxt/ctxt1.ctxt')
                    continue
            
            elif isinstance(feature, np.ndarray):
                input_feat = np.squeeze(feature)
                msg2 = he.feat_msg_generate(input_feat)
                he.encrypt(msg2, ctxt2)
               
                # threshold
                cos_thres = opt.cosine_thres
                euc_thres = opt.euc_thres
                man_thres = opt.man_thres
                
                # 1) cosine similarity measurement
                res_ctxt = he.cosin_sim(ctxt1, ctxt2)
                result = he.compare('cosine', cos_thres, res_ctxt)
                
                # # 2) euclidean distance measurement
                # res_ctxt = he.euclidean_distance(ctxt1, ctxt2)
                # result = he.compare('euclidean', euc_thres, res_ctxt)
                
                # # 3) manhattan distance measurement
                # res_ctxt = he.manhattan_distance(ctxt1, ctxt2)
                # result = he.compare('manhattan', man_thres, res_ctxt)
                
                #print similarity
                print(he.similarity_calc(res_ctxt))
            
                
                if result == "unlock":
                    frame = cv2.putText(frame, "Unlock", (350, 40), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 3, cv2.LINE_AA)
                else:
                    frame = cv2.putText(frame, "Lock", (350, 40), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 3, cv2.LINE_AA)
                
            elif isinstance(feature, int) and feature == 0:
                # Many face
                frame = cv2.putText(frame, "Too many face! ", (350, 40), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 3, cv2.LINE_AA)
            else:
                # No face
                pass
            
            cv2.imshow("test", frame)

        if cv2.waitKey(1) == 32:
            break
    
    webcam.release()
    cv2.destroyAllWindows()
