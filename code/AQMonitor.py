#!/usr/bin/python3


import time
import ctypes
import smbus
import requests
import serial
import aqi
import datetime

#Definition for Open Serial Port
port = serial.Serial("/dev/ttyS0", baudrate = 9600, timeout = 2.0)

#Definition for LPS22HB and SHTC
LPS22HB_I2C_ADDRESS   =  0x5C
LPS_ID                =  0xB1

#Register 
LPS_INT_CFG           =  0x0B        #Interrupt register
LPS_THS_P_L           =  0x0C        #Pressure threshold registers 
LPS_THS_P_H           =  0x0D        
LPS_WHO_AM_I          =  0x0F        #Who am I        
LPS_CTRL_REG1         =  0x10        #Control registers
LPS_CTRL_REG2         =  0x11
LPS_CTRL_REG3         =  0x12
LPS_FIFO_CTRL         =  0x14        #FIFO configuration register 
LPS_REF_P_XL          =  0x15        #Reference pressure registers
LPS_REF_P_L           =  0x16
LPS_REF_P_H           =  0x17
LPS_RPDS_L            =  0x18        #Pressure offset registers
LPS_RPDS_H            =  0x19        
LPS_RES_CONF          =  0x1A        #Resolution register
LPS_INT_SOURCE        =  0x25        #Interrupt register
LPS_FIFO_STATUS       =  0x26        #FIFO status register
LPS_STATUS            =  0x27        #Status register
LPS_PRESS_OUT_XL      =  0x28        #Pressure output registers
LPS_PRESS_OUT_L       =  0x29
LPS_PRESS_OUT_H       =  0x2A
LPS_TEMP_OUT_L        =  0x2B        #Temperature output registers
LPS_TEMP_OUT_H        =  0x2C
LPS_RES               =  0x33        #Filter reset register


#Label-ID
TOKEN = ""  # Token From Ubidots
DEVICE_LABEL = ""  # Device Label

#Variable
VARIABLE_LABEL_1 = "pm-2.5"  
VARIABLE_LABEL_2 = "pm-10"  
VARIABLE_LABEL_3 = "aqi-2.5"  
VARIABLE_LABEL_4 = "aqi-10"
VARIABLE_LABEL_5 = "temperature"
VARIABLE_LABEL_6 = "pressure"
VARIABLE_LABEL_7 = "humidity"


#Read Data From Serial Port
def read_pm_line (_port):
    rv = b''
    while True:
        ch1 = _port.read()
        if ch1 == b'\x42':
            ch2 = _port.read()
            if ch2 == b'\x4d':
                rv += ch1 + ch2
                rv += _port.read(28)
                return rv
 
#SHTC3 Config
class SHTC3:
    def __init__(self):
        self.dll = ctypes.CDLL("./SHTC3.so")
        init = self.dll.init
        init.restype = ctypes.c_int
        init.argtypes = [ctypes.c_void_p]
        init(None)

    def SHTC3_Read_Temperature(self):
        temperature = self.dll.SHTC3_Read_TH
        temperature.restype = ctypes.c_float
        temperature.argtypes = [ctypes.c_void_p]
        return float (temperature (None))

    def SHTC3_Read_Humidity(self):
        humidity = self.dll.SHTC3_Read_RH
        humidity.restype = ctypes.c_float
        humidity.argtypes = [ctypes.c_void_p]
        return float (humidity(None))


#LPS22HB Config
class LPS22HB:
    def __init__(self,address=LPS22HB_I2C_ADDRESS):
        self._address = address
        self._bus = smbus.SMBus(1)
        self.LPS22HB_RESET()                         #Wait for reset to complete
        self._write_byte(LPS_CTRL_REG1 ,0x02)        #Low-pass filter disabled , output registers not updated until MSB and LSB have been read , Enable Block Data Update , Set Output Data Rate to 0 
    def LPS22HB_RESET(self):
        Buf=self._read_u16(LPS_CTRL_REG2)
        Buf|=0x04                                         
        self._write_byte(LPS_CTRL_REG2,Buf)               #SWRESET Set 1
        while Buf:
            Buf=self._read_u16(LPS_CTRL_REG2)
            Buf&=0x04
            
    def LPS22HB_START_ONESHOT(self):
        Buf=self._read_u16(LPS_CTRL_REG2)
        Buf|=0x01                                         #ONE_SHOT Set 1
        self._write_byte(LPS_CTRL_REG2,Buf)
    def _read_byte(self,cmd):
        return self._bus.read_byte_data(self._address,cmd)
    def _read_u16(self,cmd):
        LSB = self._bus.read_byte_data(self._address,cmd)
        MSB = self._bus.read_byte_data(self._address,cmd+1)
        return (MSB << 8) + LSB
    def _write_byte(self,cmd,val):
        self._bus.write_byte_data(self._address,cmd,val)




#Build Payload
def build_payload(variable_1, variable_2, variable_3, variable_4, variable_5, variable_6, variable_7):
    rcv = read_pm_line(port)
    res = {##"apm10" : rcv[4]*256+rcv[5],
               ##"apm25" : rcv[6]*256+rcv[7],
               ##"apm100" : rcv[8]*256+rcv[9],
               ##"pm10" : rcv[10]*256+rcv[11],
              ## "pm25" : rcv[12]*256+rcv[13],
              ## "pm100" : rcv[14]*256+rcv[15],
               ##"gt03um" : rcv[16]*256+rcv[17],
               ##"gt05um" : rcv[18]*256+rcv[19],
               ##"gt10um" : rcv[20]*256+rcv[21],
               "gt25um" : rcv[22]*256+rcv[23],
               ##"gt50um" : rcv[24]*256+rcv[25],
               "gt100um" : rcv[26]*256+rcv[27]             
               }
    myaqi ={"aqi25" : aqi.to_aqi([(aqi.POLLUTANT_PM25, res["gt25um"])], algo=aqi.ALGO_EPA),
                "aqi100" : aqi.to_aqi([(aqi.POLLUTANT_PM10, res["gt100um"])], algo=aqi.ALGO_EPA)
            }
    

    PRESS_DATA = 0.0
    u8Buf=[0,0,0]
    lps22hb=LPS22HB()    
    lps22hb.LPS22HB_START_ONESHOT()
    shtc3 = SHTC3()
    
    if (lps22hb._read_byte(LPS_STATUS)&0x01)==0x01:  
        u8Buf[0]=lps22hb._read_byte(LPS_PRESS_OUT_XL)
        u8Buf[1]=lps22hb._read_byte(LPS_PRESS_OUT_L)
        u8Buf[2]=lps22hb._read_byte(LPS_PRESS_OUT_H)
        PRESS_DATA=((u8Buf[2]<<16)+(u8Buf[1]<<8)+u8Buf[0])/4096.0
    
        
    #Creates Value
    value_1 = res["gt25um"]  #Concentration of PM2.5 in air
    value_2 = res["gt100um"] #Concentration of PM10 in air
    value_3 = myaqi["aqi25"] #AQI 2.5 Value
    value_4 = myaqi["aqi100"]#AQI 10 Value
    value_5 = shtc3.SHTC3_Read_Temperature() #Temperature
    value_6 = PRESS_DATA #Pressure
    value_7 = shtc3.SHTC3_Read_Humidity() #Humidity
    
    payload = {variable_1: (value_1),
               variable_2: (value_2),
               variable_3: (value_3),
               variable_4: (value_4),
               variable_5: (value_5),
               variable_6: (value_6),
               variable_7: (value_7)
               }
    
    return payload

#Request Payload
def post_request(payload):
    # Creates the headers for the HTTP requests
    url = "https://industrial.api.ubidots.com"
    url = "{}/api/v1.6/devices/{}".format(url, DEVICE_LABEL)
    headers = {"X-Auth-Token": TOKEN, "Content-Type": "application/json"}

    # Makes the HTTP requests
    status = 400
    attempts = 0
    while status >= 400 and attempts <= 5:
        req = requests.post(url=url, headers=headers, json=payload)
        status = req.status_code
        attempts += 1
        time.sleep(1)

    # Processes results
    print(req.status_code, req.json())
    if status >= 400:
        print("[ERROR] Could not send data after 5 attempts, please check \
            your token credentials and internet connection")
        return False

    print("[INFO] request made properly, your device is updated")
    return True


def main():
    payload = build_payload(VARIABLE_LABEL_1, VARIABLE_LABEL_2, VARIABLE_LABEL_3, VARIABLE_LABEL_4, VARIABLE_LABEL_5, VARIABLE_LABEL_6, VARIABLE_LABEL_7)
    
    date = datetime.datetime.now()
    print(date)
    print("[INFO] Attemping to send data")
    post_request(payload)
    print("[INFO] finished")

if __name__ == '__main__':
    while (True):
        main()
        break

