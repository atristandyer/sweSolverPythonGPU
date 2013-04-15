'''
Created on Apr 3, 2013

@author: tristan
'''

import pycuda.driver as cuda
import pycuda.gpuarray as gpuarray
from dataTransfer import *
from gpuHelper import *
from spacialDiscretization import *
from fluxCalculations import *
from sourceCalculations import *
from timestepper import *
from modelChecker import *

printGPUMemUsage()

time = 0.0
dt = 0.0
runTime = 10.0
simTime = 0.0

# Build test mesh
m = 64  # number of rows
n = 64  # number of columns
freeSurface = 0.0
cellWidth = 1.0
cellHeight = 1.0

# Calculate GPU grid/block sizes
blockDim = 16
gridM = m / blockDim + (1 if (m % blockDim != 0) else 0)
gridN = n / blockDim + (1 if (n % blockDim != 0) else 0)

meshBottomIntPts = np.zeros((m + 1, n + 1, 2))
for i in range(m + 1):
    for j in range(n + 1):
        if j < n / 2:
            if j == n / 2 - 1:
                meshBottomIntPts[i][j][0] = j - 5.0
                meshBottomIntPts[i][j][1] = j - 5.0
            else:
                meshBottomIntPts[i][j][0] = j + 0.5 - 5.0
                meshBottomIntPts[i][j][1] = j - 5.0
        else:
            meshBottomIntPts[i][j][0] = n - j - 1 - 0.5 - 5.0
            meshBottomIntPts[i][j][1] = n - j - 1 - 5.0

meshU = np.zeros((m, n, 3))
for i in range(m):
    for j in range(n):
        if meshBottomIntPts[i][j][0] <= freeSurface:
            meshU[i][j][0] = freeSurface
        else:
            meshU[i][j][0] = meshBottomIntPts[i][j][0]


# Allocate memory on GPU
meshUGPU = sendToGPU(meshU)
meshUIntPtsGPU = gpuarray.zeros((m, n, 4, 3), np.float32)
meshBottomIntPtsGPU = sendToGPU(meshBottomIntPts)
meshHUVIntPtsGPU = gpuarray.zeros((m, n, 4, 3), np.float32)
meshPropSpeedsGPU = gpuarray.zeros((m, n, 4), np.float32)
meshFluxesGPU = gpuarray.zeros((m, n, 2, 3), np.float32)
meshSlopeSourceGPU = gpuarray.zeros((m, n, 2), np.float32)
meshShearSourceGPU = gpuarray.zeros((m, n), np.float32)
meshRValuesGPU = gpuarray.zeros((m, n, 3), np.float32)
meshUstarGPU = gpuarray.zeros_like(meshUGPU)

printGPUMemUsage()


# Start Timestepping
while time < runTime:

    # Reconstruct free surface
    freeSurfaceTime = reconstructFreeSurfaceTimed(meshUGPU, meshUIntPtsGPU, m, n, cellWidth, cellHeight, [blockDim, blockDim], [gridN, gridM])
    positivityTime = preservePositivityTimed(meshUIntPtsGPU, meshBottomIntPtsGPU, meshUGPU, m, n, [blockDim, blockDim], [gridN, gridM])
    huvTime = calculateHUVTimed(meshHUVIntPtsGPU, meshUIntPtsGPU, meshBottomIntPtsGPU, m, n, cellWidth, cellHeight, [blockDim, blockDim], [gridN, gridM])
    updateUTime = updateUIntPtsTimed(meshHUVIntPtsGPU, meshUIntPtsGPU, m, n, [blockDim, blockDim], [gridN, gridM])
    propSpeedTime = calculatePropSpeedsTimed(meshPropSpeedsGPU, meshHUVIntPtsGPU, m, n, [blockDim, blockDim], [gridN, gridM])

    # Calculate Fluxes and Source Terms
    fluxTime = fluxSolverTimed(meshFluxesGPU, meshUIntPtsGPU, meshBottomIntPtsGPU, meshPropSpeedsGPU, m, n, [blockDim, blockDim], [gridN, gridM])
    slopeSourceTime = solveBedSlopeTimed(meshSlopeSourceGPU, meshUIntPtsGPU, meshBottomIntPtsGPU, m, n, cellWidth, cellHeight, [blockDim, blockDim], [gridN, gridM])
    shearSourceTime = solveBedShearTimed(meshShearSourceGPU, meshUGPU, meshBottomIntPtsGPU, m, n, cellWidth, cellHeight, [blockDim, blockDim], [gridN, gridM])
    buildRTime = buildRValuesTimed(meshRValuesGPU, meshFluxesGPU, meshSlopeSourceGPU, m, n, [blockDim, blockDim], [gridN, gridM])

    # Calculate Timestep
    dt = calculateTimestep(meshPropSpeedsGPU, cellWidth)

    # Build U*
    uStarTime = buildUstarTimed(meshUstarGPU, meshUGPU, meshRValuesGPU, meshShearSourceGPU, dt, m, n, [blockDim, blockDim], [gridN, gridM])

    # Reconstruct free surface
    freeSurfaceTimeStar = reconstructFreeSurfaceTimed(meshUstarGPU, meshUIntPtsGPU, m, n, cellWidth, cellHeight, [blockDim, blockDim], [gridN, gridM])
    positivityTimeStar = preservePositivityTimed(meshUIntPtsGPU, meshBottomIntPtsGPU, meshUstarGPU, m, n, [blockDim, blockDim], [gridN, gridM])
    huvTimeStar = calculateHUVTimed(meshHUVIntPtsGPU, meshUIntPtsGPU, meshBottomIntPtsGPU, m, n, cellWidth, cellHeight, [blockDim, blockDim], [gridN, gridM])
    updateUstarTime = updateUIntPtsTimed(meshHUVIntPtsGPU, meshUIntPtsGPU, m, n, [blockDim, blockDim], [gridN, gridM])
    propSpeedStarTime = calculatePropSpeedsTimed(meshPropSpeedsGPU, meshHUVIntPtsGPU, m, n, [blockDim, blockDim], [gridN, gridM])

    # Calculate Fluxes and Source Terms
    fluxStarTime = fluxSolverTimed(meshFluxesGPU, meshUIntPtsGPU, meshBottomIntPtsGPU, meshPropSpeedsGPU, m, n, [blockDim, blockDim], [gridN, gridM])
    slopeSourceStarTime = solveBedSlopeTimed(meshSlopeSourceGPU, meshUIntPtsGPU, meshBottomIntPtsGPU, m, n, cellWidth, cellHeight, [blockDim, blockDim], [gridN, gridM])
    shearSourceStarTime = solveBedShearTimed(meshShearSourceGPU, meshUGPU, meshBottomIntPtsGPU, m, n, cellWidth, cellHeight, [blockDim, blockDim], [gridN, gridM])
    buildRStarTime = buildRValuesTimed(meshRValuesGPU, meshFluxesGPU, meshSlopeSourceGPU, m, n, [blockDim, blockDim], [gridN, gridM])

    # Build Unext
    buildUnextTime = buildUnextTimed(meshUGPU, meshUGPU, meshUstarGPU, meshRValuesGPU, meshShearSourceGPU, dt, m, n, [blockDim, blockDim], [gridN, gridM])

    timestepTime = (freeSurfaceTime + positivityTime + huvTime + updateUTime + propSpeedTime + fluxTime + slopeSourceTime + shearSourceTime + buildRTime +
                    uStarTime + freeSurfaceTimeStar + positivityTimeStar + huvTimeStar + updateUstarTime + propSpeedStarTime + fluxStarTime + slopeSourceStarTime +
                    shearSourceStarTime + buildRStarTime + buildUnextTime)

    simTime += timestepTime

    # print "Total timestep calculation time: " + str(timestepTime) + " sec"
    time += dt

print "Total simulation time: " + str(simTime) + " seconds"

# freeSurfaceTime = reconstructFreeSurfaceTimed(meshUGPU, meshUIntPtsGPU, m, n, cellWidth, cellHeight, [blockDim, blockDim], [gridN, gridM])
# positivityTime = preservePositivityTimed(meshUIntPtsGPU, meshBottomIntPtsGPU, meshUGPU, m, n, [blockDim, blockDim], [gridN, gridM])
# huvTime = calculateHUVTimed(meshHUVIntPtsGPU, meshUIntPtsGPU, meshBottomIntPtsGPU, m, n, cellWidth, cellHeight, [blockDim, blockDim], [gridN, gridM])
# updateUTime = updateUIntPtsTimed(meshHUVIntPtsGPU, meshUIntPtsGPU, m, n, [blockDim, blockDim], [gridN, gridM])
# propSpeedTime = calculatePropSpeedsTimed(meshPropSpeedsGPU, meshHUVIntPtsGPU, m, n, [blockDim, blockDim], [gridN, gridM])
# fluxTime = fluxSolverTimed(meshFluxesGPU, meshUIntPtsGPU, meshBottomIntPtsGPU, meshPropSpeedsGPU, m, n, [blockDim, blockDim], [gridN, gridM])
# slopeSourceTime = solveBedSlopeTimed(meshSlopeSourceGPU, meshUIntPtsGPU, meshBottomIntPtsGPU, m, n, cellWidth, cellHeight, [blockDim, blockDim], [gridN, gridM])
# shearSourceTime = solveBedShearTimed(meshShearSourceGPU, meshUGPU, meshBottomIntPtsGPU, m, n, cellWidth, cellHeight, [blockDim, blockDim], [gridN, gridM])
# buildRTime = buildRValuesTimed(meshRValuesGPU, meshFluxesGPU, meshSlopeSourceGPU, m, n, [blockDim, blockDim], [gridN, gridM])
# timestep = calculateTimestep(meshPropSpeedsGPU, cellWidth)
# print "Timestep: " + str(timestep)
# uStarTime = buildUstarTimed(meshUstarGPU, meshUGPU, meshRValuesGPU, meshShearSourceGPU, timestep, m, n, [blockDim, blockDim], [gridN, gridM])

# meshUIntPts = meshUIntPtsGPU.get()
# huvIntPts = meshHUVIntPtsGPU.get()
# propSpeeds = meshPropSpeedsGPU.get()
# fluxes = meshFluxesGPU.get()
# slopeSource = meshSlopeSourceGPU.get()
# shearSource = meshShearSourceGPU.get()
# RValues = meshRValuesGPU.get()


# print "Time to reconstruct free-surface:\t" + str(freeSurfaceTime) + " sec"
# print "Time to preserve positivity:\t\t" + str(positivityTime) + " sec"
# print "Time to calculate huv:\t\t\t" + str(huvTime) + " sec"
# print "Time to update U at integration points:\t" + str(updateUTime) + " sec"
# print "Time to calculate propagation speeds:\t" + str(propSpeedTime) + " sec"
# print "Time to calculate fluxes:\t\t" + str(fluxTime) + " sec"
# print "Time to calculate slope source:\t\t" + str(slopeSourceTime) + " sec"
# print "Time to calculate shear source:\t\t" + str(shearSourceTime) + " sec"
# print "Time to build R-values:\t\t\t" + str(buildRTime) + " sec"
# print "Time to build Unext:\t\t\t" + str(uStarTime) + " sec"
# print "\nTotal time:\t" + str(freeSurfaceTime + positivityTime + huvTime + updateUTime + propSpeedTime + fluxTime + slopeSourceTime + shearSourceTime + buildRTime + uStarTime)

# direction = 2
# printCellCenteredMatrix(meshU, m, n, 'meshU')
# print2DirectionInterfaceMatrix(meshBottomIntPts, m, n, direction, 'meshBottomIntPts')
# print4DirectionCellMatrix(meshUIntPts, m, n, direction, 'meshUIntPts', 0)
# print4DirectionCellMatrix(huvIntPts, m, n, direction, "huvIntPts", 0)
# print4DirectionCellMatrix(propSpeeds, m, n, 2, "propSpeeds")
# print4DirectionCellMatrix(fluxes, m, n, 1, "fluxes", 1)
# print3DMatrix(slopeSource, m, n, 0, "slopeSource")
# printCellCenteredMatrix(shearSource, m, n, "shearSource")
# printCellCenteredMatrix(RValues, m, n, "RValues", 1)

