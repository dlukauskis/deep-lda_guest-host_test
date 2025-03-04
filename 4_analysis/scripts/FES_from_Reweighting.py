#! /usr/bin/env python3

### Get the FES estimate from reweighting. 1D or 2D only ###
# uses a weighted kernel density estimation, so it requires the bandwidth sigma
# usage is similar to plumed sum_hills

import sys
import argparse
import numpy as np
import pandas as pd #much faster reading from file
use_bck=False #requires the bck.meup.sh script
if use_bck:
  import subprocess

print('')
### Parser stuff ###
parser = argparse.ArgumentParser(description='calculate the free energy surfase (FES) along the chosen collective variables (1 or 2) using a reweighted kernel density estimate')
# files
parser.add_argument('--colvar','-f',dest='filename',type=str,default='COLVAR',help='the COLVAR file name, with the collective variables and the bias')
parser.add_argument('--outfile','-o',dest='outfile',type=str,default='fes_rew.dat',help='name of the output file')
# compulsory
parser.add_argument('--sigma','-s',dest='sigma',type=str,required=True,help='the bandwidth for the kernel density estimation. Use e.g. the last value of sigma from an OPES_METAD simulation')
kbt_group=parser.add_mutually_exclusive_group(required=True)
kbt_group.add_argument('--kt',dest='kbt',type=float,help='the temperature in energy units')
kbt_group.add_argument('--temp',dest='temp',type=float,help='the temperature. Energy units is Kj/mol')
# input columns
parser.add_argument('--cv',dest='cv',type=str,default='2',help='the CVs to be used. Either by name or by column number, starting from 1')
parser.add_argument('--bias',dest='bias',type=str,default='.bias',help='the bias to be used. Either by name or by column number, starting from 1. Set to NO for nonweighted KDE')
# grid related
parser.add_argument('--min',dest='grid_min',type=str,help='lower bounds for the grid')
parser.add_argument('--max',dest='grid_max',type=str,help='upper bounds for the grid')
parser.add_argument('--bin',dest='grid_bin',type=str,default="100,100",help='number of bins for the grid')
# blocks
split_group=parser.add_mutually_exclusive_group(required=False)
split_group.add_argument('--blocks',dest='blocks_num',type=int,default=1,help='calculate errors with block average, using this number of blocks')
split_group.add_argument('--stride',dest='stride',type=int,default=0,help='print running FES estimate with this stride. Use --blocks for stride without history')
#parser.add_argument('--nohistory',dest='nohistory',action='store_true',default=False,help='FES at each stride is calculated separately. Useful for block averaging')
# other options
parser.add_argument('--deltaFat',dest='deltaFat',type=float,help='calculate the free energy difference between left and right of given cv1 value')
parser.add_argument('--skiprows',dest='skiprows',type=int,default=0,help='skip this number of initial rows')
parser.add_argument('--nomintozero',dest='nomintozero',action='store_true',default=False,help='do not shift the minimum to zero')
parser.add_argument('--der',dest='der',action='store_true',default=False,help='calculate also FES derivatives')
parser.add_argument('--fmt',dest='fmt',type=str,default='% 12.6f',help='specify the output format')
# some easy parsing
args=parser.parse_args()
if args.kbt is not None:
  kbt=args.kbt
else:
  kbt=args.temp*0.0083144621
fmt=args.fmt
calc_der=args.der
calc_deltaF=False
if args.deltaFat is not None:
  calc_deltaF=True
ts=args.deltaFat

### Get data ###
# get dim
dim=len(args.cv.split(','))
if dim==1:
  dim2=False
elif dim==2:
  dim2=True
else:
  sys.exit(' only 1D and 2D are supported')
# get cvs
f=open(args.filename,'r')
fields=f.readline().split()
if fields[1]!='FIELDS':
  sys.exit(' no FIELDS found in "%s"'%args.filename)
try:
  col_x=int(args.cv.split(',')[0])-1
  name_cv_x=fields[col_x+2]
except ValueError:
  col_x=-1
  name_cv_x=args.cv.split(',')[0]
  for i in range(len(fields)):
    if fields[i]==name_cv_x:
      col_x=i-2
  if col_x==-1:
    sys.exit(' cv "%s" not found'%name_cv_x)
  print(' cv1 "%s" found at column %d'%(name_cv_x,col_x+1))
  pass
if dim2:
  try:
    col_y=int(args.cv.split(',')[1])-1
    name_cv_y=fields[col_y+2]
  except ValueError:
    col_y=-1
    name_cv_y=args.cv.split(',')[1]
    for i in range(len(fields)):
      if fields[i]==name_cv_y:
        col_y=i-2
    if col_y==-1:
      sys.exit(' cv "%s" not found'%name_cv_y)
    print(' cv2 "%s" found at column %d'%(name_cv_y,col_y+1))
    pass
# get bias
if args.bias=='NO' or args.bias=='no':
  col_bias=[]
else:
  try:
    col_bias=[int(col)-1 for col in args.bias.split(',')]
  except ValueError:
    col_bias=[]
    if args.bias=='.bias':
      for i in range(len(fields)):
        if fields[i].find('.bias')!=-1:
          col_bias.append(i-2)
          print(' bias "%s" found at columnd %d'%(fields[i],i-1))
    else:
      for j in range(len(args.bias.split(','))):
        for i in range(len(fields)):
          if fields[i]==args.bias.split(',')[j]:
            col_bias.append(i-2)
            print(' bias "%s" found at columnd %d'%(fields[i],i-1))
      if len(col_bias)!=len(args.bias.split(',')):
        sys.exit(' found %d matching biases, but %d were requested. Use columns number to avoid ambiguity'%(len(col_bias),len(args.bias.split(','))))
    pass
# get periodicity
period_x=0
period_y=0
header_lines=1
line=f.readline().split()
while line[0]=='#!':
  header_lines+=1
  if line[2]=='min_'+name_cv_x:
    if line[3]=='-pi':
      grid_min_x=-np.pi
    else:
      grid_min_x=float(line[3])
    line=f.readline().split()
    header_lines+=1
    if line[2]!='max_'+name_cv_x:
      sys.exit(' min_%s was found, but not max_%s !'%(name_cv_x,name_cv_x))
    if line[3]=='pi':
      grid_max_x=np.pi
    else:
      grid_max_x=float(line[3])
    period_x=grid_max_x-grid_min_x
    if calc_der:
      sys.exit(' derivatives not supported with periodic CVs, remove --der option')
  if dim2 and line[2]=='min_'+name_cv_y:
    if line[3]=='-pi':
      grid_min_y=-np.pi
    else:
      grid_min_y=float(line[3])
    line=f.readline().split()
    header_lines+=1
    if line[2]!='max_'+name_cv_y:
      sys.exit(' min_%s was found, but not max_%s !'%(name_cv_y,name_cv_y))
    if line[3]=='pi':
      grid_max_y=np.pi
    else:
      grid_max_y=float(line[3])
    period_y=grid_max_y-grid_min_y
    if calc_der:
      sys.exit(' derivatives not supported with periodic CVs, remove --der option')
  line=f.readline().split()
f.close()
skipme=header_lines+args.skiprows
# get sigma
sigma_x=float(args.sigma.split(',')[0])
if dim2:
  if len(args.sigma.split(','))!=2:
    sys.exit(' two comma-separated floats expected after --sigma')
  sigma_y=float(args.sigma.split(',')[1])
# read file
all_cols=[col_x]+col_bias
if dim2:
  all_cols=[col_x,col_y]+col_bias
all_cols.sort() #pandas iloc reads them ordered
data=pd.read_table(args.filename,dtype=float,sep='\s+',comment='#',header=None,usecols=all_cols,skiprows=skipme)
cv_x=np.array(data.iloc[:,all_cols.index(col_x)])
if dim2:
  cv_y=np.array(data.iloc[:,all_cols.index(col_y)])
bias=np.zeros(len(cv_x)) #it could be that there is no bias
for col in col_bias:
  bias+=np.array(data.iloc[:,all_cols.index(col)])
bias/=kbt #dimensionless bias
del data
size=0
effsize=0

### Prepare the grid ###
grid_bin_x=int(args.grid_bin.split(',')[0])
if period_x==0:
  grid_bin_x+=1 #same as plumed sum_hills
if args.grid_min is None:
  if period_x==0: #otherwise is already set
    grid_min_x=min(cv_x)
else:
  if args.grid_min.split(',')[0]=='-pi':
    grid_min_x=-np.pi
  else:
    grid_min_x=float(args.grid_min.split(',')[0])
if args.grid_max is None:
  if period_x==0: #otherwise is already set
    grid_max_x=max(cv_x)
else:
  if args.grid_max.split(',')[0]=='pi':
    grid_max_x=np.pi
  else:
    grid_max_x=float(args.grid_max.split(',')[0])
grid_cv_x=np.linspace(grid_min_x,grid_max_x,grid_bin_x)
fes=np.zeros(grid_bin_x)
if calc_der:
  der_fes_x=np.zeros(grid_bin_x)
if dim2:
  if len(args.grid_bin.split(','))!=2:
    sys.exit('two comma separated integers expected after --bin')
  grid_bin_y=int(args.grid_bin.split(',')[1])
  if period_y==0:
    grid_bin_y+=1 #same as plumed sum_hills
  if args.grid_min is None:
    if period_y==0: #otherwise is already set
      grid_min_y=min(center_y)
  else:
    if len(args.grid_min.split(','))!=2:
      sys.exit('two comma separated floats expected after --min')
    if args.grid_min.split(',')[1]=='-pi':
      grid_min_y=-np.pi
    else:
      grid_min_y=float(args.grid_min.split(',')[1])
  if args.grid_max is None:
    if period_y==0: #otherwise is already set
      grid_max_y=max(center_y)
  else:
    if len(args.grid_max.split(','))!=2:
      sys.exit('two comma separated floats expected after --max')
    if args.grid_max.split(',')[1]=='pi':
      grid_max_y=np.pi
    else:
      grid_max_y=float(args.grid_max.split(',')[1])
  grid_cv_y=np.linspace(grid_min_y,grid_max_y,grid_bin_y)
  x,y=np.meshgrid(grid_cv_x,grid_cv_y,indexing='ij')
  fes=np.zeros((grid_bin_x,grid_bin_y))
  if calc_der:
    der_fes_x=np.zeros((grid_bin_x,grid_bin_y))
    der_fes_y=np.zeros((grid_bin_x,grid_bin_y))
deltaF=0
if calc_deltaF and (ts<=grid_min_x or ts>=grid_max_x):
  print(' +++ WARNING: the provided --deltaFat is out of the CV grid +++')
  calc_deltaF=False

### Print to file ###
# setup blocks if needed
len_tot=len(cv_x)
block_av=False
blocks_num=args.blocks_num
stride=args.stride
if blocks_num!=1:
  if calc_der:
    sys.exit(' derivatives not supported with --blocks, remove --der option')
  block_av=True
  stride=int(np.floor(len_tot/blocks_num))
  block_weight=np.zeros(blocks_num)
  fes_all=np.zeros((blocks_num,)+np.shape(fes))
if stride==0 or stride>len_tot:
  stride=len_tot
if stride!=len_tot:
  blocks_num=int(np.floor(len_tot/stride))
  print(' printing %d fes files'%(blocks_num))
  if args.outfile.rfind('/')==-1:
    prefix=''
    outfile_it=args.outfile
  else:
    prefix=args.outfile[:args.outfile.rfind('/')]
    outfile_it=args.outfile[args.outfile.rfind('/'):]
  if outfile_it.rfind('.')==-1:
    suffix=''
  else:
    suffix=outfile_it[outfile_it.rfind('.'):]
    outfile_it=outfile_it[:outfile_it.rfind('.')]
  outfile_it=prefix+outfile_it+'_%d'+suffix

# print function needs the grid and size, effsize, fes, der_fes
def printFES(outfilename,uncertainty=False):
  if use_bck:
    cmd=subprocess.Popen('bck.meup.sh -i '+outfilename,shell=True)
    cmd.wait()
  if not args.nomintozero:
    shift=np.amin(fes)
# calculate deltaF
# NB: summing is as accurate as trapz, and logaddexp avoids overflows
  if calc_deltaF:
    if not dim2:
      fesA=-kbt*np.logaddexp.reduce(-kbt*fes[grid_cv_x<ts])
      fesB=-kbt*np.logaddexp.reduce(-kbt*fes[grid_cv_x>ts])
    else:
      fesA=-kbt*np.logaddexp.reduce(-kbt*fes[x<ts])
      fesB=-kbt*np.logaddexp.reduce(-kbt*fes[x>ts])
    deltaF=fesB-fesA
#actual printing
  f=open(outfilename,'w')
  fields='#! FIELDS '+name_cv_x
  if dim2:
    fields+=' '+name_cv_y
  fields+=' file.free'
  if calc_der:
    fields+=' der_'+name_cv_x
    if dim2:
      fields+=' der_'+name_cv_y
  f.write(fields+'\n')
  f.write('#! SET sample_size %d\n'%size)
  f.write('#! SET effective_sample_size %g\n'%effsize)
  if calc_deltaF:
    f.write('#! SET DeltaF %g\n'%(deltaF))
  f.write('#! SET min_'+name_cv_x+' %g\n'%(grid_min_x))
  f.write('#! SET max_'+name_cv_x+' %g\n'%(grid_max_x))
  f.write('#! SET nbins_'+name_cv_x+' %g\n'%(grid_bin_x))
  if period_x==0:
    f.write('#! SET periodic_'+name_cv_x+' false\n')
  else:
    f.write('#! SET periodic_'+name_cv_x+' true\n')
  if not dim2:
    for i in range(grid_bin_x):
      #line=(fmt+'  '+fmt)%(grid_cv_x[i],fes[i]-shift)
      line=(f'{grid_cv_x[i]} {fes[i]-shift}')
      if calc_der:
        line+=(' '+fmt)%(der_fes_x[i])
      elif uncertainty:
        line+=(' '+fmt)%(fes_err[i])
      f.write(line+'\n')
  else:
    f.write('#! SET min_'+name_cv_y+' %g\n'%(grid_min_y))
    f.write('#! SET max_'+name_cv_y+' %g\n'%(grid_max_y))
    f.write('#! SET nbins_'+name_cv_y+' %g\n'%(grid_bin_y))
    if period_y==0:
      f.write('#! SET periodic_'+name_cv_y+' false\n')
    else:
      f.write('#! SET periodic_'+name_cv_y+' true\n')
    for i in range(grid_bin_x):
      for j in range(grid_bin_y):
        #line=(fmt+' '+fmt+'  '+fmt)%(x[i,j],y[i,j],fes[i,j]-shift)
        line=(f'{x[i,j]} {y[i,j]} {fes[i,j]-shift}')
        if calc_der:
          #line+=(' '+fmt+' '+fmt)%(der_fes_x[i,j],der_fes_y[i,j])
          line+=(f'{der_fes_x[i,j]} {der_fes_y[i,j]}')
        elif uncertainty:
          line+=(' '+fmt)%(fes_err[i,j])
        f.write(line+'\n')
      f.write('\n')
  f.close()

### Calculate FES ###
# on single grid point
def calcFESpoint(start,end,point_x,point_y=None):
  if period_x==0:
    dist_x=(point_x-cv_x[start:end])/sigma_x
  else:
    dx=np.absolute(point_x-cv_x[start:end])
    dist_x=np.minimum(dx,period_x-dx)/sigma_x
  arg=bias[start:end]-0.5*dist_x*dist_x
  if point_y is not None:
    if period_y==0:
      dist_y=(point_y-cv_y[start:end])/sigma_y
    else:
      dy=np.absolute(point_y-cv_y[start:end])
      dist_y=np.minimum(dy,period_y-dy)/sigma_y
    arg-=0.5*dist_y*dist_y
  if calc_der:
    arg_max=np.amax(arg)
    safe_kernels=np.exp(arg-arg_max)
    safe_prob=np.sum(safe_kernels)
    _fes=-kbt*(arg_max+np.log(safe_prob))
    _der_fes_x=-kbt*(np.sum(-dist_x/sigma_x*safe_kernels)/safe_prob)
    if point_y is None:
      return _fes,_der_fes_x
    else:
      _der_fes_y=-kbt*(np.sum(-dist_y/sigma_y*safe_kernels)/safe_prob)
      return _fes,_der_fes_x,_der_fes_y
  else:
    return -kbt*np.logaddexp.reduce(arg)
# adjust stride
s=len_tot%stride #skip some initial point to make it fit
if s>1:
  print(' first %d samples discarded to fit with given stride'%s)
it=1
for n in range(s+stride,len_tot+1,stride):
  if stride!=len_tot:
    print('   working...   0% of {:.0%}'.format(n/(len_tot+1)),end='\r')
# loop over whole grid
  if not dim2:
    for i in range(grid_bin_x):
      print('   working...  {:.0%}'.format(i/grid_bin_x),end='\r')
      if not calc_der:
        fes[i]=calcFESpoint(s,n,grid_cv_x[i])
      else:
        fes[i],der_fes_x[i]=calcFESpoint(s,n,grid_cv_x[i])
  else:
    for i in range(grid_bin_x):
      print('   working...  {:.0%}'.format(i/grid_bin_x),end='\r')
      for j in range(grid_bin_y):
        if not calc_der:
          fes[i,j]=calcFESpoint(s,n,x[i,j],y[i,j])
        else:
          fes[i,j],der_fes_x[i,j],der_fes_y[i,j]=calcFESpoint(s,n,x[i,j],y[i,j])
# calculate sample size
  weights=np.exp(bias[s:n]-np.amax(bias[s:n])) #these are safe to sum
  size=len(weights)
  effsize=np.sum(weights)**2/np.sum(weights**2)
# print to file
  if stride==len_tot:
    printFES(args.outfile)
  else:
    printFES(outfile_it%it)
    if block_av:
      block_weight[it-1]=np.sum(weights)
      fes_all[it-1]=fes
      s=n #do not include previous samples
    it+=1
if block_av:
  print(' printing block average to',args.outfile)
  start=len_tot%stride
  size=len_tot-start
  weights=np.exp(bias[start:]-np.amax(bias[start:]))
  effsize=np.sum(weights)**2/np.sum(weights**2)
  blocks_neff=np.sum(block_weight)**2/np.sum(block_weight**2)
  print(' number of blocsk is %d, while effective number is %g'%(blocks_num,blocks_neff))
  fes=np.average(fes_all,axis=0,weights=block_weight)
  blocks_var=blocks_neff/(blocks_neff-1)*np.average((fes_all-fes)**2,axis=0,weights=block_weight)
  fes_err=np.sqrt(blocks_var/blocks_neff)
  printFES(args.outfile,True)
print('                              ')
