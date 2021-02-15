# this didnt work, but only because of no water

import BioSimSpace as BSS

# Additional functionality from Sire.
from Sire.IO import setAmberWater
from Sire.Mol import MGName

# Load the molecular system.
files = ["system.gro","system.top"]
system = BSS.IO.readMolecules(files)

# Reformat all of the water molecules so that they match the expected
# AMBER water topology. (Here we convert to a TIP3P topology.)
waters = setAmberWater(system._sire_object.search("water"), "tip3p")

# Remove the existing water molecules from the system then loop over all
# of the new molecules and add them back in.
system.removeWaterMolecules()
for wat in waters:
    system._sire_object.add(wat, MGName("all"))

# Now save the system to AMBER format.
BSS.IO.saveMolecules('output', system, fileformat=['PRM7', 'RST7'])
