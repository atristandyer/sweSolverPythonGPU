'''
Created on Apr 8, 2013

@author: tristan
'''

import numpy as np
import pycuda.driver as cuda
import pycuda.autoinit
from pycuda.compiler import SourceModule

fluxModule = SourceModule("""

    __device__ void F(float F_vec[3], float U_vec[3], float z)
    {
        float h = U_vec[0] - z;
        if (h == 0.0f)
        {
            F_vec[0] = 0.0f;
            F_vec[1] = 0.0f;
            F_vec[2] = 0.0f;
        } else {
            F_vec[0] = U_vec[1];
            F_vec[1] = (powf(U_vec[1], 2.0f)/h) + 0.5f*9.81f*powf(h, 2.0f);
            F_vec[2] = (U_vec[1]*U_vec[2])/h;
        }
    }

    __device__ void G(float G_vec[3], float U_vec[3], float z)
    {
        float h = U_vec[0] - z;
        if (h == 0.0f)
        {
            G_vec[0] = 0.0f;
            G_vec[1] = 0.0f;
            G_vec[2] = 0.0f;
        } else {
            G_vec[0] = U_vec[2];
            G_vec[1] = (U_vec[1]*U_vec[2])/h;
            G_vec[2] = (powf(U_vec[2], 2.0f)/h) + 0.5f*9.81f*powf(h, 2.0f);
        }
    }

    __global__ void fluxSolver(float *meshFluxes, float *meshUIntPts, float *meshBottomIntPts, float *propSpeeds, int m, int n)
    {
        int row = blockIdx.y * blockDim.y + threadIdx.y + 1;
        int col = blockIdx.x * blockDim.x + threadIdx.x + 1;
        int currFluxCell = row*n*2*3 + col*2*3;
        int northIndex = row*n*4*3 + col*4*3 + 0*3;
        int upSouthIndex = (row+1)*n*4*3 + col*4*3 + 1*3;
        int eastIndex = row*n*4*3 + col*4*3 + 2*3;
        int rightWestIndex = row*n*4*3 + (col+1)*4*3 + 3*3;
        
        if (col < n-1 && row < m-1)
        {
            // North flux stuff
            float b_plus = propSpeeds[(row+1)*n*4 + col*4 + 1];
            float b_minus = propSpeeds[row*n*4 + col*4 + 0];
            if (b_plus != 0.0f || b_minus != 0.0f)
            {
                float U_north[3] = {meshUIntPts[northIndex], meshUIntPts[northIndex+1], meshUIntPts[northIndex+2]};
                float U_south[3] = {meshUIntPts[upSouthIndex], meshUIntPts[upSouthIndex+1], meshUIntPts[upSouthIndex+2]};
                float B = meshBottomIntPts[(row+1)*(n+1)*2 + col*2]; 
                float G_north[3], G_south[3];
                G(G_north, U_north, B);
                G(G_south, U_south, B);
                
                for (int i=0; i<3; i++)
                {
                    meshFluxes[currFluxCell + i] = (b_plus*G_north[i] - b_minus*G_south[i])/(b_plus-b_minus) + ((b_plus*b_minus)/(b_plus-b_minus))*(U_south[i] - U_north[i]);
                }
            } else {
                for (int i=0; i<3; i++)
                {
                    meshFluxes[currFluxCell + i] = 0.0f;
                }
            }
            
            // East flux stuff
            float a_plus = propSpeeds[row*n*4 + (col+1)*4 + 3];
            float a_minus = propSpeeds[row*n*4 + col*4 + 2];
            if (a_plus != 0.0f || a_minus != 0.0f)
            {
                float U_east[3] = {meshUIntPts[eastIndex], meshUIntPts[eastIndex+1], meshUIntPts[eastIndex+2]};
                float U_west[3] = {meshUIntPts[rightWestIndex], meshUIntPts[rightWestIndex+1], meshUIntPts[rightWestIndex+2]};
                float B = meshBottomIntPts[row*(n+1)*2 + (col+1)*2 + 1];
                float F_east[3], F_west[3];
                F(F_east, U_east, B);
                F(F_west, U_west, B);
                
                for (int i=0; i<3; i++)
                {
                    meshFluxes[currFluxCell + 3 + i] = (a_plus*F_east[i] - a_minus*F_west[i])/(a_plus-a_minus) + ((a_plus*a_minus)/(a_plus-a_minus))*(U_west[i] - U_east[i]);
                }
            } else {
                for (int i=0; i<3; i++)
                {
                    meshFluxes[currFluxCell + 3 + i] = 0.0f;
                }
            }
        }
    }
    
    __global__ void buildRValues(float *meshRValues, float *meshFluxes, float *meshSlopeSource, float *meshWindShear, int m, int n)
    {
        int row = blockIdx.y * blockDim.y + threadIdx.y + 2;
        int col = blockIdx.x * blockDim.x + threadIdx.x + 2;
        
        if (col < n-2 && row < m-2)
        {
            meshRValues[row*n*3 + col*3] = 0.0f - (meshFluxes[row*n*2*3 + col*2*3 + 3] - meshFluxes[row*n*2*3 + (col-1)*2*3 + 3]) - (meshFluxes[row*n*2*3 + col*2*3] - meshFluxes[(row-1)*n*2*3 + col*2*3]);
            meshRValues[row*n*3 + col*3 + 1] = meshWindShear[row*n*2 + col*2] + meshSlopeSource[row*n*2 + col*2] - (meshFluxes[row*n*2*3 + col*2*3 + 4] - meshFluxes[row*n*2*3 + (col-1)*2*3 + 4]) - (meshFluxes[row*n*2*3 + col*2*3 + 1] - meshFluxes[(row-1)*n*2*3 + col*2*3 + 1]);
            meshRValues[row*n*3 + col*3 + 2] = meshWindShear[row*n*2 + col*2 + 1] + meshSlopeSource[row*n*2 + col*2 + 1] - (meshFluxes[row*n*2*3 + col*2*3 + 5] - meshFluxes[row*n*2*3 + (col-1)*2*3 + 5]) - (meshFluxes[row*n*2*3 + col*2*3 + 2] - meshFluxes[(row-1)*n*2*3 + col*2*3 + 2]);
        }
    }

""")


fluxSolverGPU = fluxModule.get_function("fluxSolver")
buildRValuesGPU = fluxModule.get_function("buildRValues")

def fluxSolver(meshFluxesGPU, meshUIntPtsGPU, meshBottomIntPtsGPU, meshPropSpeedsGPU, m, n, blockDims, gridDims):

    fluxSolverGPU(meshFluxesGPU, meshUIntPtsGPU, meshBottomIntPtsGPU, meshPropSpeedsGPU,
                  np.int32(m), np.int32(n),
                  block=(blockDims[0], blockDims[1], 1), grid=(gridDims[0], gridDims[1]))

def fluxSolverTimed(meshFluxesGPU, meshUIntPtsGPU, meshBottomIntPtsGPU, meshPropSpeedsGPU, m, n, blockDims, gridDims):

    return fluxSolverGPU(meshFluxesGPU, meshUIntPtsGPU, meshBottomIntPtsGPU, meshPropSpeedsGPU,
                  np.int32(m), np.int32(n),
                  block=(blockDims[0], blockDims[1], 1), grid=(gridDims[0], gridDims[1]), time_kernel=True)

def buildRValues(meshRValuesGPU, meshFluxesGPU, meshSlopeSourceGPU, meshWindShearGPU, m, n, blockDims, gridDims):

    buildRValuesGPU(meshRValuesGPU, meshFluxesGPU, meshSlopeSourceGPU, meshWindShearGPU,
                    np.int32(m), np.int32(n),
                    block=(blockDims[0], blockDims[1], 1), grid=(gridDims[0], gridDims[1]))

def buildRValuesTimed(meshRValuesGPU, meshFluxesGPU, meshSlopeSourceGPU, meshWindShearGPU, m, n, blockDims, gridDims):

    return buildRValuesGPU(meshRValuesGPU, meshFluxesGPU, meshSlopeSourceGPU, meshWindShearGPU,
                    np.int32(m), np.int32(n),
                    block=(blockDims[0], blockDims[1], 1), grid=(gridDims[0], gridDims[1]), time_kernel=True)
