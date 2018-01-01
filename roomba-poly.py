#!/usr/bin/env python3
"""
This is a NodeServer for Wi-Fi enabled Roomba vacuums by fahrer16 (Brian Feeney)
Based on template for Polyglot v2 written in Python2/3 by Einstein.42 (James Milne) milne.james@gmail.com
"""

import polyinterface
import sys
import json
from threading import Timer
from roomba import Roomba


LOGGER = polyinterface.LOGGER
SERVERDATA = json.load(open('server.json'))
VERSION = SERVERDATA['credits'][0]['version']

STATES = {  "charge": 1, #"Charging"
            "new": 2, #"New Mission"
            "run": 3, #"Running"
            "resume":4, #"Running"
            "hmMidMsn": 5, #"Recharging"
            "recharge": 6, #"Recharging"
            "stuck": 7, #"Stuck"
            "hmUsrDock": 8, #"User Docking"
            "dock": 9, #"Docking"
            "dockend": 10, # "Docking - End Mission"
            "cancelled": 11, #"Cancelled"
            "stop": 12, #"Stopped"
            "pause": 13, #"Paused"
            "hmPostMsn": 14, #"End Mission"
            "": 0}

RUNNING_STATES = {2,3,4,5,6}

ERROR_MESSAGES = {
        0: "None",
        1: "Roomba is stuck with its left or right wheel hanging down.",
        2: "The debris extractors can't turn.",
        5: "The left or right wheel is stuck.",
        6: "The cliff sensors are dirty, it is hanging over a drop, "\
           "or it is stuck on a dark surface.",
        8: "The fan is stuck or its filter is clogged.",
        9: "The bumper is stuck, or the bumper sensor is dirty.",
        10: "The left or right wheel is not moving.",
        11: "Roomba has an internal error.",
        14: "The bin has a bad connection to the robot.",
        15: "Roomba has an internal error.",
        16: "Roomba has started while moving or at an angle, or was bumped "\
            "while running.",
        17: "The cleaning job is incomplete.",
        18: "Roomba cannot return to the Home Base or starting position."
    }

class Controller(polyinterface.Controller):
    """
    The Controller Class is the primary node from an ISY perspective. It is a Superclass
    of polyinterface.Node so all methods from polyinterface.Node are available to this
    class as well.

    Class Variables:
    self.nodes: Dictionary of nodes. Includes the Controller node. Keys are the node addresses
    self.name: String name of the node
    self.address: String Address of Node, must be less than 14 characters (ISY limitation)
    self.polyConfig: Full JSON config dictionary received from Polyglot.
    self.added: Boolean Confirmed added to ISY as primary node

    Class Methods (not including the Node methods):
    start(): Once the NodeServer config is received from Polyglot this method is automatically called.
    addNode(polyinterface.Node): Adds Node to self.nodes and polyglot/ISY. This is called for you
                                 on the controller itself.
    delNode(address): Deletes a Node from the self.nodes/polyglot and ISY. Address is the Node's Address
    longPoll(): Runs every longPoll seconds (set initially in the server.json or default 10 seconds)
    shortPoll(): Runs every shortPoll seconds (set initially in the server.json or default 30 seconds)
    query(): Queries and reports ALL drivers for ALL nodes to the ISY.
    runForever(): Easy way to run forever without maxing your CPU or doing some silly 'time.sleep' nonsense
                  this joins the underlying queue query thread and just waits for it to terminate
                  which never happens.
    """
    def __init__(self, polyglot):
        super().__init__(polyglot)
        self.name = 'Roomba Bridge'
        self._nodeQueue = []
        self._roombas = {}
        self.discoveryTries = 0
        _msg = "Connection timer created for roomba controller"
        self.timer = Timer(1,LOGGER.debug,[_msg])

    def start(self):
        LOGGER.info('Starting Roomba Polyglot v2 NodeServer version {}'.format(VERSION))
        self.connectionTime = 5 #TODO: Add configurable time period here
        self.discover()

    def shortPoll(self):
        for node in self.nodes:
            self.nodes[node].updateInfo()

    def longPoll(self):
        pass

    def query(self):
        for node in self.nodes:
            self.nodes[node].reportDrivers()

    def _addRoombaNodesFromQueue(self):
        if len(self._nodeQueue) > 0:
            LOGGER.debug('Attempting to add %i roombas that have connected', len(self._nodeQueue))
            for _address in self._nodeQueue:
                try:
                    if _address in self.nodes:
                        #Node has already been added, take it out of the queue
                        self._nodeQueue.remove(_address)
                        LOGGER.debug('%s already in ISY', _address)
                    else:
                        _roomba = self._roombas[_address]
                        LOGGER.debug('Processing %s (%s) for addition', _roomba.roombaName, _address)
                        #Check that info has been received from roomba by checking for a key that should be there regardless of roomba's capabilities (MAC address):
                        if len(_roomba.master_state["state"]["reported"]["mac"]) > 0:
                            try:
                                _name = str(_roomba.roombaName)
                                LOGGER.debug('Getting capabilities from %s', _name)
                                _hasPose = self._getCapability(_roomba, 'pose')
                                _hasCarpetBoost = self._getCapability(_roomba, 'carpetBoost')
                                _hasBinFullDetect = self._getCapability(_roomba, 'binFullDetect')
                                LOGGER.debug('Capabilities for %s: Position: %s, CarpetBoost: %s, BinFullDetection: %s', _name, str(_hasPose), str(_hasCarpetBoost), str(_hasBinFullDetect))
                                if  _hasCarpetBoost:
                                    LOGGER.info('Adding Roomba 980: %s (%s)', _name, _address)
                                    self.addNode(Roomba980(self, self.address, _address, _name, _roomba))
                                    self._nodeQueue.remove(_address)
                                elif _hasPose:
                                    LOGGER.info('Adding Series 900 Roomba: %s (%s)', _name, _address)
                                    self.addNode(Series900Roomba(self, self.address, _address, _name, _roomba))
                                    self._nodeQueue.remove(_address)
                                elif _hasBinFullDetect:
                                    LOGGER.info('Adding Series 800 Roomba: %s (%s)', _name, _address)
                                    self.addNode(Series800Roomba(self, self.address, _address, _name, _roomba))
                                    self._nodeQueue.remove(_address)
                                else:
                                    LOGGER.info('Adding Base Roomba: %s (%s)', _name, _address)
                                    self.addNode(BasicRoomba(self, self.address, _address, _name, _roomba))
                                    self._nodeQueue.remove(_address)
                            except Exception as ex:
                                LOGGER.error('Error adding %s after discovery: %s', _name, str(ex))
                        else:
                            LOGGER.debug('Information not yet received for %s', _name)
                except Exception as ex:
                    LOGGER.debug('Information not yet received from %s', _roomba.roombaName)
            if len(self._nodeQueue) > 0 and self.discoveryTries <= 2: #There are still roomba's to add, we'll restart the timer to run this routine again
                LOGGER.debug('%i roombas are still pending addition', len(self._nodeQueue))
                self.discoveryTries += 1
                self._startRoombaConnectionDelayTimer()
        else:
            LOGGER.debug('No roombas pending addition')

    def discover(self, *args, **kwargs):
        LOGGER.debug('Beginning Discovery on %s', str(self.name))
        try:
            _items = 0
            self.discoveryTries = 0
            _params = self.polyConfig['customParams']
            for key,value in _params.items():
                _key = key.lower()
                if _key.startswith('vacuum') or _key.startswith('roomba'):
                    _items += 1
                    try:
                        if 'ip' in value and 'blid' in value and 'password' in value and 'name' in value:
                            _value = json.loads(value)
                            _ip = _value['ip']
                            _blid = _value['blid']
                            _password = _value['password']
                            _name = _value['name']
                            _address = 'rm' + _blid[-10:]

                            if _address not in self.nodes: #Check that node hasn't already been added to ISY
                                if _address not in self._nodeQueue: #Check that node hasn't already been added to queue of roombas to be added to ISY
                                    LOGGER.debug('Connecting to %s', _name)
                                    _roomba = Roomba(_ip, _blid, _password, roombaName = _name)
                                    _roomba.nodeAddress = _address
                                    _roomba.connect()
                                    #build a list of the roombas that need to be added.  We'll check them later after it's had a chance to connect
                                    self._nodeQueue.append(_address)
                                    self._roombas[_address] = _roomba
                                else:
                                    LOGGER.debug('%s already pending addition to ISY. Skipping addition.', _name)
                            else:
                                LOGGER.debug('%s already configured. Skipping addition to ISY.', _name)
                    except Exception as ex:
                        LOGGER.error('Error with Roomba Connection: %s', str(ex))
            if _items == 0:
                LOGGER.error('No Roombas are configured in Polyglot.  For each Roomba, add a key starting with "vacuum" and a value containing the IP address, BLID, Password, and Name.  Example: "{"ip":"192.168.3.36", "blid":"6945841021309640","password":":1:1512838259:R0dzOYDrIVQHJFcR","name":"Upstairs Roomba"}".  Note the use of double quotes.  Static IP\'s are strongly recommended.  See here for instructions how to get BLID and Password: "https://github.com/NickWaterton/Roomba980-Python"')
            elif len(self._nodeQueue) > 0:
                LOGGER.info('%i Roomba\'s identified in configuration', _items)
                self._startRoombaConnectionDelayTimer()
            else:
                LOGGER.debug('Discovery: No new roombas need to be added to ISY')
        except Exception as ex:
            LOGGER.error('Error with Roomba Discovery: %s', str(ex))

    def _startRoombaConnectionDelayTimer(self):
        try:
            if self.timer is not None:
                self.timer.cancel()
            self.timer = Timer(self.connectionTime, self._addRoombaNodesFromQueue)
            self.timer.start()
            LOGGER.debug("Starting roomba connection delay timer for %s seconds", str(self.connectionTime))
            return True
        except Exception as ex:
            LOGGER.error('Error starting roomba connection delay timer: %s', str(ex))
            return False
    
    def _getCapability(self, roomba, capability):
        #If a capability is not contained within the roomba's master_state, it doesn't have that capability.  Not sure it could ever be set to 0, but this will ensure it is 1 in order to report it has the capability
        try:
            return roomba.master_state["state"]["reported"]["cap"][capability] == 1
        except:
            return False

    def updateInfo(self):
        pass #Nothing to update for controller node

    def delete(self):
        LOGGER.info('Deleting roomba controller node.  Deleting sub-nodes...')
        for node in self.nodes:
            if node.address != self.address:
                self.nodes[node].delete()


    id = 'controller'
    commands = {'DISCOVER': discover}
    drivers = [{'driver': 'ST', 'value': 0, 'uom': 2}]


class BasicRoomba(polyinterface.Node):
    """
    This is the Base Class for all Roombas as all Roomba's contain the features within.  Other Roomba's build upon these features.
    """
    def __init__(self, parent, primary, address, name, roomba):
        super().__init__(parent, primary, address, name)
        self.roomba = roomba
        self.connected = False

    def start(self):
        self.updateInfo()

    def setOn(self, command):
        #Roomba Start Command (not to be confused with the node start command above)
        LOGGER.info('Received Start Command on %s', self.name)
        try:
            self.roomba.send_command("start")
            return True
        except Exception as ex:
            LOGGER.error('Error processing Roomba Start Command on %s: %s', self.name, str(ex))
            return False

    def setOff(self, command):
        #Roomba Stop Command
        LOGGER.info('Received Stop Command on %s', self.name)
        try:
            self.roomba.send_command("stop")
            return True
        except Exception as ex:
            LOGGER.error('Error processing Roomba Stop Command on %s: %s', self.name, str(ex))
            return False

    def setPause(self, command):
        #Roomba Pause Command
        LOGGER.info('Received Pause Command on %s', self.name)
        try:
            self.roomba.send_command("pause")
            return True
        except Exception as ex:
            LOGGER.error('Error processing Roomba Pause Command on %s: %s', self.name, str(ex))
            return False

    def setResume(self, command):
        #Roomba Resume Command
        LOGGER.info('Received Resume Command on %s', self.name)
        try:
            self.roomba.send_command("resume")
            return True
        except Exception as ex:
            LOGGER.error('Error processing Roomba Resume Command on %s: %s', self.name, str(ex))
            return False

    def setDock(self, command):
        #Roomba Dock Command
        LOGGER.info('Received Dock Command on %s', self.name)
        try:
            self.roomba.send_command("dock")
            return True
        except Exception as ex:
            LOGGER.error('Error processing Roomba Dock Command on %s: %s', self.name, str(ex))
            return False

    def _updateBasicProperties(self):
        #LOGGER.debug('Setting Basic Properties for %s', self.name)

        #ST (On/Off)
        #GV1, States (Enumeration)
        try:
            _state = self.roomba.master_state["state"]["reported"]["cleanMissionStatus"]["phase"]
            #LOGGER.debug('Current state on %s: %s', self.name, str(_state))
            if _state in STATES:
                self.setDriver('GV1', STATES[_state])
                _running = (STATES[_state] in RUNNING_STATES)
                self.setDriver('ST', (0,100)[int(_running)])
        except Exception as ex:
            LOGGER.error("Error updating current state on %s: %s", self.name, str(ex))

        #GV2, Connected (True/False)
        try:
            _connected = self.roomba.roomba_connected
            if _connected == False and self.connected == True:
                LOGGER.error('Roomba Disconnected: %s', self.name)
            elif _connected == True and self.connected == False:
                LOGGER.info('Roomba Connected: %s', self.name)
            self.connected = _connected

            self.setDriver('GV2', int(_connected))

        except Exception as ex:
            LOGGER.error("Error updating connection status on %s: %s", self.name, str(ex))

        #BATLVL, Battery (Percent)
        try:
            _batPct = self.roomba.master_state["state"]["reported"]["batPct"]
            self.setDriver('BATLVL', _batPct)
        except Exception as ex:
            LOGGER.error("Error updating battery Percentage on %s: %s", self.name, str(ex))

        #GV3, Bin Present (True/False)
        try:
            _binPresent = self.roomba.master_state["state"]["reported"]["bin"]["present"]
            self.setDriver('GV3', int(_binPresent))
        except Exception as ex:
            LOGGER.error("Error updating Bin Present on %s: %s", self.name, str(ex))

        #GV4, Wifi Signal (Percent)
        try:
            _rssi = self.roomba.master_state["state"]["reported"]["signal"]["rssi"]
            _quality = int(max(min(2.* (_rssi + 100.),100),0))
            self.setDriver('GV4', _quality)
        except Exception as ex:
            LOGGER.error("Error updating WiFi Signal Strength on %s: %s", self.name, str(ex))

        #GV5, Runtime (Hours)
        try:
            _hr = self.roomba.master_state["state"]["reported"]["bbrun"]["hr"]
            _min = self.roomba.master_state["state"]["reported"]["bbrun"]["min"]
            _runtime = round(_hr + _min/60.,1)
            self.setDriver('GV5', _runtime)
        except Exception as ex:
            LOGGER.error("Error updating runtime on %s: %s", self.name, str(ex))

        #GV6, Error Actie (True/False)
        #ALARM, Error (Enumeration)
        try:
            if "error" in self.roomba.master_state["state"]["reported"]["cleanMissionStatus"]:
                _error = self.roomba.master_state["state"]["reported"]["cleanMissionStatus"]["error"]
            else: _error = 0

            self.setDriver('GV6', int(_error != 0))
            self.setDriver('ALARM', _error)
        except Exception as ex:
            LOGGER.error("Error updating current Error Status on %s: %s", self.name, str(ex))
    
    def delete(self):
        try:
            LOGGER.info("Deleting %s and attempting to stop communication to roomba", self.name)
            self.roomba.disconnect()
        except Exception as ex:
            LOGGER.error("Error attempting to stop communication to %s: %s", self.name, str(ex))

    def updateInfo(self):
        self._updateBasicProperties()

    def query(self, command=None):
        self.updateInfo()
        self.reportDrivers()


    drivers = [{'driver': 'ST', 'value': 0, 'uom': 78}, #Running (On/Off)
               {'driver': 'GV1', 'value': 0, 'uom': 25}, #State (Enumeration)
               {'driver': 'GV2', 'value': 0, 'uom': 2}, #Connected (True/False)
               {'driver': 'BATLVL', 'value': 0, 'uom': 51}, #Battery (percent)
               {'driver': 'GV3', 'value': 0, 'uom': 2}, #Bin Present (True/False)
               {'driver': 'GV4', 'value': 0, 'uom': 51}, #Wifi Signal (Percent)
               {'driver': 'GV5', 'value': 0, 'uom': 20}, #RunTime (Hours)
               {'driver': 'GV6', 'value': 0, 'uom':2}, #Error Active (True/False)
               {'driver': 'ALARM', 'value': 0, 'uom':25} #Current Error (Enumeration)
               ]
    id = 'basicroomba'
    commands = {
                    'DON': setOn, 'DOF': setOff, 'PAUSE': setPause, 'RESUME': setResume, 'DOCK': setDock, 'QUERY':query
                }

class Series800Roomba(BasicRoomba):
    """
    This class builds upon the BasicRoomba class by adding full bin detection present in the 800 series roombas
    """
    def setOn(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setOn(command)

    def setOff(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setOff(command)

    def setPause(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setPause(command)

    def setResume(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setResume(command)

    def setDock(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setDock(command)

    def _update800SeriesProperties(self):
        #LOGGER.debug('Setting Bin status and settings for %s', self.name)

        #GV7, Bin Full (True/False)
        try:
            _binFull = self.roomba.master_state["state"]["reported"]["bin"]["full"]
            self.setDriver('GV7', int(_binFull))
        except Exception as ex:
            LOGGER.error("Error updating Bin Full on %s: %s", self.name, str(ex))

        #GV8, Behavior on Full Bin (Enumeration, 1=Finish, 0=Continue)
        try:
            _finishOnBinFull = self.roomba.master_state["state"]["reported"]["binPause"]
            self.setDriver('GV8', int(_finishOnBinFull))
        except Exception as ex:
            LOGGER.error("Error updating Behavior on Bin Full Setting on %s: %s", self.name, str(ex))

    def updateInfo(self):
        super().updateInfo()
        self._update800SeriesProperties()

    def query(self, command=None):
        super().updateInfo()

    def setBinFinish(self,command=None):
        LOGGER.info('Received Command to set Bin Finish on %s: %s', self.name, str(command))
        try:
            _setting = command.get('value')
            self.roomba.set_preference("binPause", ("false","true")[int(_setting)]) # 0=Continue, 1=Finish
        except Exception as ex:
            LOGGER.error("Error setting Bin Finish Parameter on %s: %s", self.name, str(ex))

    drivers = [{'driver': 'ST', 'value': 0, 'uom': 78}, #Running (On/Off)
               {'driver': 'GV1', 'value': 0, 'uom': 25}, #State (Enumeration)
               {'driver': 'GV2', 'value': 0, 'uom': 2}, #Connected (True/False)
               {'driver': 'BATLVL', 'value': 0, 'uom': 51}, #Battery (percent)
               {'driver': 'GV3', 'value': 0, 'uom': 2}, #Bin Present (True/False)
               {'driver': 'GV4', 'value': 0, 'uom': 51}, #Wifi Signal (Percent)
               {'driver': 'GV5', 'value': 0, 'uom': 20}, #RunTime (Hours)
               {'driver': 'GV6', 'value': 0, 'uom':2}, #Error Active (True/False)
               {'driver': 'ALARM', 'value': 0, 'uom':25}, #Current Error (Enumeration)
               {'driver': 'GV7', 'value': 0, 'uom': 2}, #Bin Present (True/False)
               {'driver': 'GV8', 'value': 0, 'uom': 25} #Behavior on Full Bin (Enumeration - Finish/Continue)
               ]
    id = 'series800roomba'
    commands = {
                    'DON': setOn, 'DOF': setOff, 'PAUSE': setPause, 'RESUME': setResume, 'DOCK': setDock, 'QUERY':query, 'SET_BIN_FINISH': setBinFinish
                }

class Series900Roomba(Series800Roomba):
    """
    This class builds upon the Series800Roomba class by adding position tracking present in the 900 series roombas
    """
    def setOn(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setOn(command)

    def setOff(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setOff(command)

    def setPause(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setPause(command)

    def setResume(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setResume(command)

    def setDock(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setDock(command)

    def _update900SeriesProperties(self):
        #LOGGER.debug('Setting Position status for %s', self.name)

        #GV9, X Position
        try:
            _x = self.roomba.master_state["state"]["reported"]["pose"]["point"]["x"]
            self.setDriver('GV9', int(_x))
        except Exception as ex:
            LOGGER.error("Error updating X Position on %s: %s", self.name, str(ex))

        #GV10, Y Position
        try:
            _y = self.roomba.master_state["state"]["reported"]["pose"]["point"]["y"]
            self.setDriver('GV10', int(_y))
        except Exception as ex:
            LOGGER.error("Error updating Y Position on %s: %s", self.name, str(ex))

        #ROTATE, Theta (degrees)
        try:
            _theta = self.roomba.master_state["state"]["reported"]["pose"]["theta"]
            self.setDriver('ROTATE', int(_theta))
        except Exception as ex:
            LOGGER.error("Error updating Theta Position on %s: %s", self.name, str(ex))

        #LOGGER.debug('Getting Passes setting for %s', self.name)

        #GV11, Passes Setting (0="", 1=One, 2=Two, 3=Automatic)
        try:
            _noAutoPasses = self.roomba.master_state["state"]["reported"]["noAutoPasses"]
            _twoPass = self.roomba.master_state["state"]["reported"]["twoPass"]
            if not _noAutoPasses:
                self.setDriver('GV11', 3)
            elif _twoPass:
                self.setDriver('GV11', 2)
            else:
                self.setDriver('GV11', 1)
        except Exception as ex:
            LOGGER.error("Error updating Passes Setting on %s: %s", self.name, str(ex))

        #GV12, Edge Clean (On/Off)
        try:
            _openOnly = self.roomba.master_state["state"]["reported"]["openOnly"]
            self.setDriver('GV12', (100,0)[int(_openOnly)]) #note 0,100 order (openOnly True means Edge Clean is Off)
        except Exception as ex:
            LOGGER.error("Error updating Edge Clean Setting on %s: %s", self.name, str(ex))


    def updateInfo(self):
        super().updateInfo()
        self._update900SeriesProperties()

    def query(self, command=None):
        super().updateInfo()

    def setBinFinish(self,command=None):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setBinFinish(command)

    def setPasses(self,command=None):
        LOGGER.info('Received Command to set Number of Passes on %s: %s', self.name, str(command))
        try:
            _setting = int(command.get('value'))
            if _setting == 1: #One Pass
                self.roomba.set_preference("noAutoPasses", "true")
                self.roomba.set_preference("twoPass", "false")
            elif _setting == 2: #Two Passes
                self.roomba.set_preference("noAutoPasses", "true")
                self.roomba.set_preference("twoPass", "true")
            elif _setting == 3: #Automatic Passes
                self.roomba.set_preference("noAutoPasses", "false")
        except Exception as ex:
            LOGGER.error("Error setting Number of Passes on %s: %s", self.name, str(ex))

    def setEdgeClean(self,command=None):
        LOGGER.info('Received Command to set Edge Clean on %s: %s', self.name, str(command))
        try:
            _setting = int(command.get('value'))
            if _setting == 100:
                self.roomba.set_preference("openOnly", "false")
            else:
                self.roomba.set_preference("openOnly", "true")
        except Exception as ex:
            LOGGER.error("Error setting Edge Clean on %s: %s", self.name, str(ex))

    drivers = [{'driver': 'ST', 'value': 0, 'uom': 78}, #Running (On/Off)
               {'driver': 'GV1', 'value': 0, 'uom': 25}, #State (Enumeration)
               {'driver': 'GV2', 'value': 0, 'uom': 2}, #Connected (True/False)
               {'driver': 'BATLVL', 'value': 0, 'uom': 51}, #Battery (percent)
               {'driver': 'GV3', 'value': 0, 'uom': 2}, #Bin Present (True/False)
               {'driver': 'GV4', 'value': 0, 'uom': 51}, #Wifi Signal (Percent)
               {'driver': 'GV5', 'value': 0, 'uom': 20}, #RunTime (Hours)
               {'driver': 'GV6', 'value': 0, 'uom':2}, #Error Active (True/False)
               {'driver': 'ALARM', 'value': 0, 'uom':25}, #Current Error (Enumeration)
               {'driver': 'GV7', 'value': 0, 'uom': 2}, #Bin Present (True/False)
               {'driver': 'GV8', 'value': 0, 'uom': 25}, #Behavior on Full Bin (Enumeration - Finish/Continue)
               {'driver': 'GV9', 'value': 0, 'uom': 56}, #X Position (Raw Value)
               {'driver': 'GV10', 'value': 0, 'uom': 56}, #Y Position (Raw Value)
               {'driver': 'ROTATE', 'value': 0, 'uom': 14}, #Theta (Degrees)
               {'driver': 'GV11', 'value': 0, 'uom': 25}, #Passes Setting (Enumeration, One/Two/Automatic)
               {'driver': 'GV12', 'value': 0, 'uom': 78} #Edge Clean (On/Off)
               ]
    id = 'series900roomba'
    commands = {
                    'DON': setOn, 'DOF': setOff, 'PAUSE': setPause, 'RESUME': setResume, 'DOCK': setDock, 'QUERY':query, 'SET_BIN_FINISH': setBinFinish, 'SET_PASSES': setPasses, 'SET_EDGE_CLEAN': setEdgeClean
                }

class Roomba980(Series900Roomba):
    """
    This class builds upon the Series900Roomba class by adding fan settings (Carpet Boost)
    """
    def setOn(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setOn(command)

    def setOff(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setOff(command)

    def setPause(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setPause(command)

    def setResume(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setResume(command)

    def setDock(self, command):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setDock(command)

    def _update980Properties(self):
        #LOGGER.debug('Updating status for Roomba 980 %s', self.name)

        #GV13, Fan Speed Setting (0="", 1=Eco, 2=Automatic, 3=Performance)
        try:
            _carpetBoost = self.roomba.master_state["state"]["reported"]["carpetBoost"]
            _vacHigh = self.roomba.master_state["state"]["reported"]["vacHigh"]
            if _carpetBoost:
                self.setDriver('GV13', 2)
            elif _vacHigh:
                self.setDriver('GV13', 3)
            else:
                self.setDriver('GV13', 1)
        except Exception as ex:
            LOGGER.error("Error updating Fan Speed Setting on %s: %s", self.name, str(ex))

    def updateInfo(self):
        super().updateInfo()
        self._update980Properties()

    def query(self, command=None):
        super().updateInfo()

    def setBinFinish(self,command=None):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setBinFinish(command)

    def setPasses(self,command=None):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setPasses(command)

    def setEdgeClean(self,command=None):
        #Although method is not different than the BasicRoomba class, this needs to be defined so that it can be specified in "commands" 
        super().setEdgeClean(command)

    def setFanSpeed(self,command=None): 
        LOGGER.info('Received Command to set Fan Speed on %s: %s', self.name, str(command))
        try:
            _setting = int(command.get('value'))
            #(0="", 1=Eco, 2=Automatic, 3=Performance)
            if _setting == 1: #Eco
                LOGGER.info('Setting %s fan speed to "Eco"', self.name)
                self.roomba.set_preference("carpetBoost", "false")
                self.roomba.set_preference("vacHigh", "false")
            elif _setting == 2: #Automatic
                LOGGER.info('Setting %s fan speed to "Automatic" (Carpet Boost Enabled)', self.name)
                self.roomba.set_preference("carpetBoost", "true")
                self.roomba.set_preference("vacHigh", "false")
            elif _setting == 3: #Performance
                LOGGER.info('Setting %s fan speed to "Perfomance" (High Fan Speed)', self.name)
                self.roomba.set_preference("carpetBoost", "false")
                self.roomba.set_preference("vacHigh", "true")
        except Exception as ex:
            LOGGER.error("Error setting Number of Passes on %s: %s", self.name, str(ex))

    drivers = [{'driver': 'ST', 'value': 0, 'uom': 78}, #Running (On/Off)
               {'driver': 'GV1', 'value': 0, 'uom': 25}, #State (Enumeration)
               {'driver': 'GV2', 'value': 0, 'uom': 2}, #Connected (True/False)
               {'driver': 'BATLVL', 'value': 0, 'uom': 51}, #Battery (percent)
               {'driver': 'GV3', 'value': 0, 'uom': 2}, #Bin Present (True/False)
               {'driver': 'GV4', 'value': 0, 'uom': 51}, #Wifi Signal (Percent)
               {'driver': 'GV5', 'value': 0, 'uom': 20}, #RunTime (Hours)
               {'driver': 'GV6', 'value': 0, 'uom':2}, #Error Active (True/False)
               {'driver': 'ALARM', 'value': 0, 'uom':25}, #Current Error (Enumeration)
               {'driver': 'GV7', 'value': 0, 'uom': 2}, #Bin Present (True/False)
               {'driver': 'GV8', 'value': 0, 'uom': 25}, #Behavior on Full Bin (Enumeration - Finish/Continue)
               {'driver': 'GV9', 'value': 0, 'uom': 56}, #X Position (Raw Value)
               {'driver': 'GV10', 'value': 0, 'uom': 56}, #Y Position (Raw Value)
               {'driver': 'ROTATE', 'value': 0, 'uom': 14}, #Theta (Degrees)
               {'driver': 'GV11', 'value': 0, 'uom': 25}, #Passes Setting (Enumeration, One/Two/Automatic)
               {'driver': 'GV12', 'value': 0, 'uom': 78}, #Edge Clean (On/Off)
               {'driver': 'GV13', 'value': 0, 'uom': 25} #Fan Speed Setting (Enumeration)
               ]
    id = 'roomba980'
    commands = {
                    'DON': setOn, 'DOF': setOff, 'PAUSE': setPause, 'RESUME': setResume, 'DOCK': setDock, 'QUERY':query, 'SET_BIN_FINISH': setBinFinish, 'SET_PASSES': setPasses, 'SET_EDGE_CLEAN': setEdgeClean, 'SET_FAN_SPEED': setFanSpeed
                }

if __name__ == "__main__":
    try:
        polyglot = polyinterface.Interface('Roomba')
        polyglot.start()
        control = Controller(polyglot)
        control.runForever()
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
