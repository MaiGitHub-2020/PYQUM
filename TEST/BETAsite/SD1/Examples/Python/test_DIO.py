import sys
sys.path.append('C:\Program Files (x86)\Keysight\SD1\Libraries\Python')

import keysightSD1



# change slot number to your value
SLOT = 8

# CREATE AND OPEN MODULE
module = keysightSD1.SD_DIO()
print("Module name:", module.getProductName())
print("slot:", module.getSlot())
print("Chassis: %s\n" %module.getChassis())

# MODULE CONSTANTS
CHASSIS = '0'
moduleID = module.openWithSlot("M3102A", CHASSIS, SLOT)


if moduleID < 0:
	print("Module open error:", moduleID)
else:
	print("Module opened:", moduleID)
	print("Module name:", module.getProductName())
	print("slot:", module.getSlot())
	print("Chassis:", module.getChassis())
	print()
	
	# CONFIGURE AND START DAQ
	POINTS_PER_CYCLE = 1000
	CYCLES = 1
	TRIGGER_DELAY = 0
	CHANNEL = 1

	print(module.DAQconfig(CHANNEL, POINTS_PER_CYCLE, CYCLES, TRIGGER_DELAY, keysightSD1.SD_TriggerModes.EXTTRIG))
	print(module.DAQstart(CHANNEL))
	
	# READ DATA
	TIMEOUT = 1000

	dataRead = module.DAQread(CHANNEL, POINTS_PER_CYCLE * CYCLES, TIMEOUT)
	print("Data: %s" %dataRead)

	# exiting...
	module.close()
	print()
	print("DIO closed")
