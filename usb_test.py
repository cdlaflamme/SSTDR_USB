#usb_test.py
#searches for SSTDR devices and prints output. Used for testing usb environment

import usb

all_devices = usb.core.find(find_all=True)
print("All Devices:\n")
if all_devices is None:
    print("None")
else:
    print(list(all_devices))

vendor_devices = usb.core.find(find_all=True, idVendor=0x067b)
print("Devices with matching Vendor ID:")
if vendor_devices is None:
    print("None")
else:
    print(list(vendor_devices))

product_devices = usb.core.find(find_all=True, idProduct=0x2303)
print("Devices with matching Product ID:")
if product_devices is None:
    print("None")
else:
    print(list(product_devices))

exact_device = usb.core.find(find_all=True, idVendor=0x067b, idProduct=0x2303)
print("Exact matches:")
if exact_device is None:
    print("None")
else:
    print(list(exact_device))