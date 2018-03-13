import sys
import numpy as np
import scipy as sp
import matplotlib.pyplot as plt
import _pickle as pickle

from mrai import mrai_cnn
from mrai import util

''' Parse experiment parameters '''

# Number of labeled target samples
nT = int(sys.argv[1])

# Which iteration
it = int(sys.argv[2])

# Width and height of image
imw = 256
imh = 256

# Margin
margin = 1

# Number of epochs
nE = 32

# Batch size
bS = 128

# Number of repeats
nR = 10

# Patch dimension, size and unraveled size
pD = 7
pW = 2*pD+1
pU = pW**2

# Classes
K = np.array([1, 2, 3])
nK = len(K)

# Subsample size
sS = 10

# Regularization
l2 = 0.001
c_range = np.logspace(-3, 6, 10)

# Linear or nonlinear classifier
cmplx = 'loglin'

# Number of folds for cross-validation performance
num_folds = 2

# vizualisations
sav = True
viz = True

# Preallocate classifier result arrays
err = {}

''' Initialize network '''

# Initalize acquisition-invariant network
net = mrai_cnn(margin=margin, nE=nE, bS=bS, pD=pD, K=K, sS=sS, nT=nT, l2=l2, w=imw, h=imh)
net.compile_net()

''' Load Brainweb data '''

if viz:
    tgtprdSub = 20
    brainwebSub = np.arange(19)
else:
    brainwebSub = np.arange(20)

# Select subjects for training and testing
nI = 4
nJ = 1
nH = 9
sourceSub = np.random.choice(brainwebSub, size=nI, replace=False)
targetSub = np.random.choice(np.setdiff1d(brainwebSub, sourceSub), size=nJ, replace=False)
tgtvalSub = np.random.choice(np.setdiff1d(brainwebSub, np.concatenate((sourceSub,targetSub))), size=nH, replace=False)

# Source data
fnI = []
fnL = []
for i in range(nI):
    fnI.append("/home/wmkouw/Data/Brainweb/sims/subject"+str(sourceSub[i]+1).zfill(2)+"_256_GE2D_1.5T_RSS.raw")
    fnL.append("/home/wmkouw/Data/Brainweb/phantoms/subject"+str(sourceSub[i]+1).zfill(2)+"_256.raw")
I = util.subject2image(fnI, w=256,h=256, norm_pix=True)
L = util.subject2image(fnL, w=256,h=256, seg=True)

# Skull strip
I = net.strip_skull(I,L==0)

# Target data
fnJ = []
fnU = []
for j in range(nJ):
    fnJ.append("/home/wmkouw/Data/Brainweb/sims/subject"+str(targetSub[j]+1).zfill(2)+"_256_GE2D_3.0T_MRB.raw")
    fnU.append("/home/wmkouw/Data/Brainweb/phantoms/subject"+str(targetSub[j]+1).zfill(2)+"_256.raw")
J = util.subject2image(fnJ, w=256,h=256, norm_pix=True)
U = util.subject2image(fnU, w=256,h=256, seg=True)

# Skull strip
J = net.strip_skull(J, U==0)

# Target validation
fnH = []
fnQ = []
for h in range(nH):
    fnH.append("/home/wmkouw/Data/Brainweb/sims/subject"+str(tgtvalSub[h]+1).zfill(2)+"_256_GE2D_3.0T_MRB.raw")
    fnQ.append("/home/wmkouw/Data/Brainweb/phantoms/subject"+str(tgtvalSub[h]+1).zfill(2)+"_256.raw")
H = util.subject2image(fnH, w=256,h=256, norm_pix=True)
Q = util.subject2image(fnQ, w=256,h=256, seg=True)

# Skull strip
H = net.strip_skull(H, Q==0)

if viz:
    # Target prediction
    P = util.subject2image(["/home/wmkouw/Data/Brainweb/sims/subject"+str(tgtprdSub).zfill(2)+"_256_GE2D_3.0T_MRB.raw"], w=256,h=256, norm_pix=True)
    R = util.subject2image(["/home/wmkouw/Data/Brainweb/phantoms/subject"+str(tgtprdSub).zfill(2)+"_256.raw"], w=256,h=256, seg=True)

    # Skull strip
    P = net.strip_skull(P,R==0)

# Target labels to use
tix = np.zeros((nJ,nK,nT), dtype='int64')
jp = np.zeros((nJ*nK*nT,pW,pW,1), dtype='float64')
up = np.zeros((nJ*nK*nT,), dtype='int64')
c = 0
for j in range(nJ):
    for k in range(nK):

        # Find tissue in image
        Ujk = np.argwhere(U[j][pD:-pD-1,pD:-pD-1]==K[k])+pD

        # Sample from target sub 1 index with label k
        tix[j,k,:] = np.random.choice(np.ravel_multi_index(Ujk.T, (imw,imh)), size=(nT,))

        # Extract patch at index
        jp[c*nT:(c+1)*nT,:,:,:] = net.index2patch(J[j], index=tix[j,k,:])
        up[c*nT:(c+1)*nT] = K[k]

        # Tick up
        c += 1


''' Sample patches and compare source/target classifiers '''

# Sample source patches
Ip,Lp = net.image2patch(I,L)

# Sample target within-subject validation patches
Jp,Up = net.image2patch(J,U)

# Sample target between-subject validation patches
Hp,Qp = net.image2patch(H,Q)

# Propagate samples through network
Ih = net.propagate(Ip, scan_ID=0)
jh = net.propagate(jp, scan_ID=1)
Jh = net.propagate(Jp, scan_ID=1)
Hh = net.propagate(Hp, scan_ID=1)

# Combinations of datasets
Lup = np.concatenate((Lp,up), axis=0)
UQp = np.concatenate((Up,Qp), axis=0)

Ijp = np.concatenate((Ip,jp), axis=0)
JHp = np.concatenate((Jp,Hp), axis=0)
JHh = np.concatenate((Jh,Hh), axis=0)

if viz:
    util.viz_embedding(net, Ih,Lp,Jh,Up, savefn='viz/b1b3_cnn_'+'_nT'+str(nT)+'_r'+str(it)+'embedding_untrained.png')

# Train standard tissue classifiers
# err['tiss-J-source'] = util.classify(Ip,Lp, val=(Jp,Up), complexity='cnn', num_epochs=nE, batch_size=bS)
# err['tiss-J-srctgt'] = util.classify(Ijp,Lup, val=(Jp,Up), complexity='cnn', num_epochs=nE, batch_size=bS)
# err['tiss-J-target'] = util.classify(jp,up, val=(Jp,Up), complexity='cnn', num_epochs=nE, batch_size=bS)
err['tiss-H-source'] = util.classify(Ip,Lp, val=(Hp,Qp), complexity='cnn', num_epochs=nE, batch_size=bS)
err['tiss-H-srctgt'] = util.classify(Ijp,Lup, val=(Hp,Qp), complexity='cnn', num_epochs=nE, batch_size=bS)
err['tiss-H-target'] = util.classify(jp,up, val=(Hp,Qp), complexity='cnn', num_epochs=nE, batch_size=bS)
# err['tiss-A-source'] = util.classify(Ip,Lp, val=(JHp,UQp), complexity='cnn', num_epochs=nE, batch_size=bS)
# err['tiss-A-srctgt'] = util.classify(Ijp,Lup, val=(JHp,UQp), complexity='cnn', num_epochs=nE, batch_size=bS)
# err['tiss-A-target'] = util.classify(jp,up, val=(JHp,UQp), complexity='cnn', num_epochs=nE, batch_size=bS)

# # Scanner labels
LU = np.concatenate((np.ones(Lp.shape), -np.ones(Up.shape)), axis=0)
LQ = np.concatenate((np.ones(Lp.shape), -np.ones(Qp.shape)), axis=0)
LB = np.concatenate((np.ones(Lp.shape), -np.ones(UQp.shape)), axis=0)

# # Scanner classifier on raw image patches
IJ = np.concatenate((Ip,Jp), axis=0).reshape((Ip.shape[0]+Jp.shape[0],-1))
IH = np.concatenate((Ip,Hp), axis=0).reshape((Ip.shape[0]+Hp.shape[0],-1))
IA = np.concatenate((Ip,JHp), axis=0).reshape((Ip.shape[0]+JHp.shape[0],-1))
# err['scan-J-source'] = util.classify(IJ, LU, num_folds=num_folds, complexity=cmplx)
err['scan-H-source'] = util.classify(IH, LQ, num_folds=num_folds, complexity=cmplx)
# err['scan-A-source'] = util.classify(IA, LB, num_folds=num_folds, complexity=cmplx)

# ''' Untrained network '''

# # Scanner classifier on untrained network
IJ = np.concatenate((Ih,Jh), axis=0).reshape((Ip.shape[0]+Jh.shape[0],-1))
IH = np.concatenate((Ih,Hh), axis=0).reshape((Ip.shape[0]+Hh.shape[0],-1))
IA = np.concatenate((Ih,JHh), axis=0).reshape((Ip.shape[0]+JHh.shape[0],-1))
# err['scan-J-net-un'] = util.classify(IJ, LU, num_folds=num_folds, complexity=cmplx)
err['scan-H-net-un'] = util.classify(IH, LQ, num_folds=num_folds, complexity=cmplx)
# err['scan-A-net-un'] = util.classify(IA, LB, num_folds=num_folds, complexity=cmplx)

# # Tissue classifier on untrained net
# err['tiss-J-net-un'] = util.classify(Ih,Lp, val=(Jh,Up), complexity=cmplx)
err['tiss-H-net-un'] = util.classify(Ih,Lp, val=(Hh,Qp), complexity=cmplx)
# err['tiss-A-net-un'] = util.classify(Ih,Lp, val=(JHh,UQp), complexity=cmplx)


''' Training '''

# Repeat training procedure
for r in range(nR):

    # Report progress
    print('At repetition '+str(r+1).zfill(2)+' of '+str(nR))

    # Train
    net.train(I, L, J, tix)


# Re-propagate samples through network
Ih = net.propagate(Ip, scan_ID=0)
jh = net.propagate(jp, scan_ID=1)
Jh = net.propagate(Jp, scan_ID=1)
Hh = net.propagate(Hp, scan_ID=1)

Ijh = np.concatenate((Ih,jh), axis=0)
JHh = np.concatenate((Jh,Hh), axis=0)

if viz:
    util.viz_embedding(net, Ih,Lp,Jh,Up, savefn='viz/b1b3_cnn_'+'_nT'+str(nT)+'_r'+str(it)+'embedding_trained.png')

''' Performance trained network '''

# Scanner classifier on trained network
IJ = np.concatenate((Ih,Jh), axis=0).reshape((Ip.shape[0]+Jh.shape[0],-1))
IH = np.concatenate((Ih,Hh), axis=0).reshape((Ip.shape[0]+Hh.shape[0],-1))
IA = np.concatenate((Ih,JHh), axis=0).reshape((Ip.shape[0]+JHh.shape[0],-1))
# err['scan-J-net-tn'] = util.classify(IJ, LU, num_folds=num_folds, complexity=cmplx)
err['scan-H-net-tn'] = util.classify(IH, LQ, num_folds=num_folds, complexity=cmplx)
# err['scan-A-net-tn'] = util.classify(IA, LB, num_folds=num_folds, complexity=cmplx)

# Tissue classifier on trained network
# err['tiss-J-net-tn'] = util.classify(Ih,Lp, val=(Jh,Up), complexity=cmplx)
err['tiss-H-net-tn'] = util.classify(Ih,Lp, val=(Hh,Qp), complexity=cmplx)
# err['tiss-A-net-tn'] = util.classify(Ih,Lp, val=(JHh,UQp), complexity=cmplx)
# err['tiss-J-net-tt'] = util.classify(Ijh,Lup, val=(Jh,Up), complexity=cmplx)
err['tiss-H-net-tt'] = util.classify(Ijh,Lup, val=(Hh,Qp), complexity=cmplx)
# err['tiss-A-net-tt'] = util.classify(Ijh,Lup, val=(JHh,UQp), complexity=cmplx)

''' Write results '''

if sav:
    # File name
    fn = 'results/err_exp_acqinv_cnn_b1b3_nT'+str(nT)+'_r'+str(it)+'.pickle'
    print('Writing to: '+fn)

    # Save error dict
    with open(fn, 'wb') as handle:
        pickle.dump(err, handle)

''' vizualizations '''

if viz:

    # Source classifiers prediction
    clsf_src = util.classifier(Ip,Lp, complexity='cnn')
    clsf_src.fit(Ip,ks.utils.to_categorical(Lp - np.min(Lp),nK), batch_size=bS, epochs=2*nE, verbose=1)
    Ph = net.segmentImage(clsf_src,P[0,:,:], clfr='cnn', patch_dim=(pW,pW))
    Ph[R[0,pD:-pD,pD:-pD]==0] = 0
    savefn = 'viz/b1b3_pred_src_sub'+str(tgtprdSub)+'_nT'+str(nT)+'_r'+str(it)+'.png'
    print('Writing image to : '+savefn)
    util.viz_segmentation(Ph, savefn=savefn)

    # Src+tgt classifiers prediction
    clsf_spt = util.classifier(Ijp,Lup, complexity='cnn')
    clsf_spt.fit(Ijp,ks.utils.to_categorical(Lup - np.min(Lup),nK), batch_size=bS, epochs=2*nE, verbose=1)
    Ph = net.segmentImage(clsf_spt,P[0,:,:], clfr='cnn', patch_dim=(pW,pW))
    Ph[R[0,pD:-pD,pD:-pD]==0] = 0
    savefn = 'viz/b1b3_pred_spt_sub'+str(tgtprdSub)+'_nT'+str(nT)+'_r'+str(it)+'.png'
    print('Writing image to : '+savefn)
    util.viz_segmentation(Ph, savefn=savefn)

    # Network classifiers prediction
    clsf_net = util.classifier(Ih,Lp, complexity=cmplx)
    clsf_net.fit(Ih,Lp)
    Ph = net.segmentImage(clsf_net,P[0,:,:], clfr='svm', patch_dim=(pW,pW), scan_ID=1)
    Ph[R[0,pD:-pD,pD:-pD]==0] = 0
    savefn = 'viz/b1b3_pred_net_sub'+str(tgtprdSub)+'_nT'+str(nT)+'_r'+str(it)+'.png'
    print('Writing image to : '+savefn)
    util.viz_segmentation(Ph, savefn=savefn)

    # Net_tt classifiers prediction
    clsf_ntt = util.classifier(Ijh,Lup, complexity=cmplx)
    clsf_ntt.fit(Ijh,Lup)
    Ph = net.segmentImage(clsf_ntt,P[0,:,:], clfr='svm', patch_dim=(pW,pW), scan_ID=1)
    Ph[R[0,pD:-pD,pD:-pD]==0] = 0
    savefn = 'viz/b1b3_pred_ntt_sub'+str(tgtprdSub)+'_nT'+str(nT)+'_r'+str(it)+'.png'
    print('Writing image to : '+savefn)
    util.viz_segmentation(Ph, savefn=savefn)

    # Target classifiers prediction
    clsf_tgt = util.classifier(jp,up, complexity='cnn')
    clsf_tgt.fit(jp,ks.utils.to_categorical(up - np.min(up),nK), batch_size=bS, epochs=2*nE, verbose=1)
    Ph = net.segmentImage(clsf_tgt,P[0,:,:], clfr='cnn', patch_dim=(pW,pW))
    Ph[R[0,pD:-pD,pD:-pD]==0] = 0
    savefn = 'viz/b1b3_pred_tgt_sub'+str(tgtprdSub)+'_nT'+str(nT)+'_r'+str(it)+'.png'
    print('Writing image to : '+savefn)
    util.viz_segmentation(Ph, savefn=savefn)

    # vizualize data and true segmentation
    util.viz_segmentation(P[0], savefn='viz/b1b3_data_tgt_sub'+str(tgtprdSub)+'_nT'+str(nT)+'_r'+str(it)+'.png', cmap='gray')
    util.viz_segmentation(R[0], savefn='viz/b1b3_true_tgt_sub'+str(tgtprdSub)+'_nT'+str(nT)+'_r'+str(it)+'.png')
