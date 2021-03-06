import numpy as np
from cmath import *
from func import *
import scipy
import scipy.linalg
from pyscf import gto, dft, scf, ao2mo

class fields:
    """
    A class which manages field perturbations. Mirrors TCL_FieldMatrices.h
    """
    def __init__(self,the_scf_, params_):
        self.dip_ints = None # AO dipole integrals.
        self.dip_ints_bo = None
        self.nuc_dip = None
        self.dip_mo = None # Nuclear dipole (AO)
        self.Generate(the_scf_)
        self.fieldAmplitude = params_["FieldAmplitude"]
        self.tOn = params_["tOn"]
        self.Tau = params_["Tau"]
        self.FieldFreq = params_["FieldFreq"]
        self.pol = np.array([params_["ExDir"],params_["EyDir"],params_["EzDir"]])
        self.pol0 = None
        self.pol0AA = None
        return

    def Generate(self,the_scf):
        """
        Performs the required PYSCF calls to generate the AO basis dipole matrices.
        """
        self.dip_ints = the_scf.mol.intor('cint1e_r_sph', comp=3) # component,ao,ao.
        dip_ints_mo = self.dip_ints.copy()
        dip_ints_mo[0] = TransMat(self.dip_ints[0],the_scf.mo_coeff)
        dip_ints_mo[1] = TransMat(self.dip_ints[1],the_scf.mo_coeff)
        dip_ints_mo[2] = TransMat(self.dip_ints[2],the_scf.mo_coeff)
        # print dip_ints_mo.shape
        self.dip_ints_mo = 0.5 * (dip_ints_mo[0] + dip_ints_mo[0].T.conj())
        self.dip_ints_mo = 0.5 * (dip_ints_mo[1] + dip_ints_mo[1].T.conj())
        self.dip_ints_mo = 0.5 * (dip_ints_mo[2] + dip_ints_mo[2].T.conj())
        #print "A dipole matrices\n",self.dip_ints
        charges = the_scf.mol.atom_charges()
        coords  = the_scf.mol.atom_coords()
        self.nuc_dip = np.einsum('i,ix->x', charges, coords)
        return

    def Update(self,c_mat):
        '''
        Args:
            c_mat: Transformation matrix (AOx??)
        Updates dip_int to (?? x ??)
        '''
        #self.dip_mo = self.dip_ints.astype(complex).copy()
        #self.dip_mo[0] = TransMat(self.dip_ints[0],c_mat,-1)
        #self.dip_mo[1] = TransMat(self.dip_ints[1],c_mat,-1)
        #self.dip_mo[2] = TransMat(self.dip_ints[2],c_mat,-1)
        return


    def AppAmp(self,time, par = None):
        if (par.params["ApplyImpulse"] == 1):
            return self.ImpulseAmp(time)
        elif (par.params["ApplyCw"] == 1):
            return self.CWAmp(time)
        else:
            return
    def ImpulseAmp(self,time):
        amp = self.fieldAmplitude*np.sin(self.FieldFreq*time)*(1.0/sqrt(2.0*3.1415*self.Tau*self.Tau))*np.exp(-1.0*np.power(time-self.tOn,2.0)/(2.0*self.Tau*self.Tau))
        IsOn = False
        if (np.abs(amp)>pow(10.0,-9.0)):
            IsOn = True
        return amp,IsOn

    def CWAmp(self,time):
        amp = self.fieldAmplitude * np.sin(self.FieldFreq*time)
        return amp, True


    def InitializeExpectation(self,rho0_, C_,nA = None, U = None):
        self.pol0 = self.Expectation(rho0_,C_)
        # print self.dip_ints[0]
        # print self.dip_ints[1]
        # print self.dip_ints[2]
        if nA != None:
            self.dip_ints_bo = self.dip_ints.copy()
            for i in range(3):
                self.dip_ints_bo[i] = TransMat(self.dip_ints[i],U)
            self.pol0AA = self.Expectation(rho0_,C_,True,nA)


    def ApplyField(self, a_mat, time):
        """
        Args:
            a_mat: an AO matrix to which the field is added.
            time: current time.
        Returns:
            a_mat + dipole field at this time.
            IsOn
        """
        amp, IsOn = self.AppAmp(time)
        mpol = self.pol * amp
        if (IsOn):
            print "Field on"
            return a_mat + 2.0*np.einsum("kij,k->ij",self.dip_ints,mpol), True
        else:
            return a_mat, False

    def ApplyFieldBO(self, a_mat, time,par = None):
        """
        Same as apply field, but this applies a projector to only perturb a part of the system
        Args:
            a_mat: an MO matrix to which the field is added.
            c_mat: a AO=>MO coefficient matrix.
            time: current time.
        Return
            a_mat + dipole field at this time.
            IsOn
        """
        amp, IsOn = self.AppAmp(time, par)
        mpol = self.pol * amp # [x,y,z] * C
        if (IsOn):
            return a_mat + 2.0 * np.einsum("kij,k->ij",self.dip_ints_bo, mpol), True
        else :
            return a_mat, False

    def ApplyField(self, a_mat, c_mat, time, par = None):
        """
        Args:
            a_mat: an MO matrix to which the field is added.
            c_mat: a AO=>MO coefficient matrix.
            time: current time.
        Returns:
            a_mat + dipole field at this time.
            IsOn
        """
        amp, IsOn = self.AppAmp(time, par)
        mpol = self.pol * amp
        if (IsOn):
            return a_mat + 2.0*TransMat(np.einsum("kij,k->ij",self.dip_ints,mpol),c_mat), True
            #return a_mat + 2.0*np.einsum("kij,k->ij",self.dip_ints_mo,mpol), True
        else :
            return a_mat, False

    def Expectation(self, rho_, C_, AA = False, nA = None,U = None):
        """
        Args:
            rho_: current MO density.
            C_: current AO=> Mo Transformation. (ao X mo)
        Returns:
            [<Mux>,<Muy>,<Muz>]
        """
        # At this point convert both into MO and then calculate the dipole...
        rhoAO = TransMat(rho_,C_,-1)
        if (AA):
            # first try in AO basis, if it does not work then in BO
            e_dip = np.einsum('xij,ji->x', self.dip_ints_bo[:,:nA,:nA], rhoAO[:nA,:nA])
            if (self.pol0AA != None):
                return e_dip - self.pol0AA
            else:
                return e_dip
        else:
            mol_dip = np.einsum('xij,ji->x', self.dip_ints, rhoAO)
            #print self.pol0
            if (np.any(self.pol0) != None):
                return mol_dip - self.pol0#2.0*np.einsum("ij,jik->k",rhoMO,muMO) - self.pol0
            else:
                return mol_dip#2.0*np.einsum("ij,jik->k",rhoMO,muMO)
