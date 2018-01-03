#!/usr/bin/env python3
"""
This is a NodeServer for Rachio irrigation controllers by fahrer16 (Brian Feeney)
Based on template for Polyglot v2 written in Python2/3 by Einstein.42 (James Milne) milne.james@gmail.com
"""

import polyinterface
import sys
from socket import error as socket_error
from copy import deepcopy
import json, time
from threading import Timer #Added version 2.2.0 for node addition queue
from rachiopy import Rachio
 
LOGGER = polyinterface.LOGGER
SERVERDATA = json.load(open('server.json'))
VERSION = SERVERDATA['credits'][0]['version']

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
        super(Controller, self).__init__(polyglot)
        self.name = 'Rachio Bridge'
        #Queue for nodes to be added in order to prevent a flood of nodes from being created on discovery.  Added version 2.2.0
        self.nodeQueue = {}
        _msg = "Connection timer created for node addition queue"
        self.timer = Timer(1,LOGGER.debug,[_msg])
        self.nodeAdditionInterval = 1

    def start(self):
        LOGGER.info('Starting Rachio Polyglot v2 NodeServer version {}'.format(VERSION))
        try:
            if 'api_key' in self.polyConfig['customParams']:
                self.api_key = self.polyConfig['customParams']['api_key']
            else:
                LOGGER.error('Rachio API key required in order to establish connection.  Enter custom parameter of \'api_key\' in Polyglot configuration.  See "https://rachio.readme.io/v1.0/docs" for instructions on how to obtain Rachio API Key.')
                return False
        except Exception as ex:
            LOGGER.error('Error reading Rachio API Key from Polyglot Configuration: %s', str(ex))
            return False

        #Get Node Addition Interval from Polyglot Configuration (Added version 2.2.0)
        try:
            if 'nodeAdditionInterval' in self.polyConfig['customParams']:
                _nodeAdditionInterval = self.polyConfig['customParams']['nodeAdditionInterval']
                if _nodeAdditionInterval >= 0 and _nodeAdditionInterval <= 60:
                    self.nodeAdditionInterval = _nodeAdditionInterval
                else:
                    LOGGER.error('Node Addition Interval configured but outside of permissible range of 0 - 60 seconds, defaulting to %s second(s)', str(self.nodeAdditionInterval))
            else:
                LOGGER.info('Node Addition Interval not configured, defaulting to %s second(s).  If a different time is needed, enter a custom parameter with a key of \'nodeAdditionInterval\' and a value in seconds in order to change interval.', str(self.nodeAdditionInterval))
        except Exception as ex:
            LOGGER.error('Error reading Rachio Node Addition Interval from Polyglot Configuration: %s', str(ex))

        self.discover()

    def shortPoll(self):
        pass

    def longPoll(self):
        try:
            for node in self.nodes:
                self.nodes[node].update_info()
        except Exception as ex:
            LOGGER.error('Error running longPoll on %s: %s', self.name, str(ex))

    def update_info(self, force=False):
        #Nothing to update for this node
        pass

    def query(self):
        try:
            for node in self.nodes:
                self.nodes[node].update_info(force=True)
        except Exception as ex:
            LOGGER.error('Error running query on %s: %s', self.name, str(ex))

    def discoverCMD(self, command=None):
        # This is command called by ISY discover button
        for node in self.nodes:
            self.nodes[node].discover()

    def discover(self, command=None):
        LOGGER.info('Starting discovery on %s', self.name)
        try:
            self.r_api = Rachio(self.api_key)
            _person_id = self.r_api.person.getInfo()
            self.person_id = _person_id[1]['id']
            self.person = self.r_api.person.get(self.person_id) #returns json containing all info associated with person (devices, zones, schedules, flex schedules, and notifications)
        except Exception as ex:
            LOGGER.error('Connection Error on RachioControl discovery, may be temporary. %s', str(ex))
            return False

        try:
            #get devices
            _devices = self.person[1]['devices']
            LOGGER.info('%i Rachio controllers found. Adding to ISY', len(_devices))
            for d in _devices:
                _device_id = str(d['id'])

                _name = str(d['name'])
                _address = str(d['macAddress']).lower()
                if _address not in self.nodes:
                    #LOGGER.info('Adding Rachio Controller: %s(%s)', _name, _address)
                    self.addNodeQueue(RachioController(self, _address, _address, _name, d))

        except Exception as ex:
            LOGGER.error('Error during Rachio device discovery: %s', str(ex))

        return True

    def addNodeQueue(self, node):
        #If node is not already in ISY, add the node.  Otherwise, queue it for addition and start the interval timer.  Added version 2.2.0
        try:
            LOGGER.debug('Request received to add node: %s (%s)', node.name, node.address)
            #if not self.poly.getNode(node.address):
            self.nodeQueue[node.address] = node
            self._startNodeAdditionDelayTimer()
            #else:
            #    self.addNode(node)
        except Exception as ex:
            LOGGER.error('Error queuing node for addition: %s'. str(ex))

    def _startNodeAdditionDelayTimer(self): #Added version 2.2.0
        try:
            if self.timer is not None:
                self.timer.cancel()
            self.timer = Timer(self.nodeAdditionInterval, self._addNodesFromQueue)
            self.timer.start()
            LOGGER.debug("Starting node addition delay timer for %s second(s)", str(self.nodeAdditionInterval))
            return True
        except Exception as ex:
            LOGGER.error('Error starting node addition delay timer: %s', str(ex))
            return False

    def _addNodesFromQueue(self): #Added version 2.2.0
        try:
            if len(self.nodeQueue) > 0:
                for _address in self.nodeQueue:
                    LOGGER.debug('Adding %s(%s) from queue', self.name, self.address)
                    self.addNode(self.nodeQueue[_address])
                    del self.nodeQueue[_address]
                    break #only add one node at a time
        
            if len(self.nodeQueue) > 0: #Check for more nodes after addition, if there are more to addd, restart the timer
                self._startNodeAdditionDelayTimer()
            else:
                LOGGER.info('No nodes pending addition')
        except Exception as ex:
            LOGGER.error('Error encountered adding node from queue: %s', str(ex))


    def delete(self):
        LOGGER.info('Deleting %s', self.name)

    id = 'rachio'
    commands = {'DISCOVER': discoverCMD}
    drivers = [{'driver': 'ST', 'value': 0, 'uom': 2}]


class RachioController(polyinterface.Node):
    def __init__(self, parent, primary, address, name, device):
        super().__init__(parent, primary, address, name)
        self.isPrimary = True
        self.primary = primary
        self.parent = parent
        self.device = device
        self.device_id = device['id']
        self.rainDelay_minutes_remaining = 0
        self.currentSchedule = []
        self.scheduleItems = []
        self._tries = 0
        self.runTypes = {0: "NONE",
                              1: "AUTOMATIC",
                              2: "MANUAL",
                              3: "OTHER"}

        self.scheduleTypes = {0: "NONE",
                              1: "FIXED",
                              2: "FLEX",
                              3: "OTHER"}

    def start(self):
        self.update_info()
        self.discover()

    def discover(self, command=None):
        _success = True
        LOGGER.info('Discovering nodes on Rachio Controller %s (%s)', self.name, self.address)
        try:
            _zones = self.device['zones']
            LOGGER.info('%i Rachio zones found on "%s" controller. Adding to ISY', len(_zones), self.name)
            for z in _zones:
                _zone_id = str(z['id'])
                _zone_num = str(z['zoneNumber'])
                _zone_addr = self.address + _zone_num #construct address for this zone (mac address of controller appended with zone number) because ISY limit is 14 characters
                _zone_name = str(z['name'])
                if _zone_addr not in self.parent.nodes:
                    #LOGGER.info('Adding new Rachio Zone to %s Controller, %s(%s)', self.name, _zone_name, _zone_addr)
                    self.parent.addNodeQueue(RachioZone(self.parent, self.address, _zone_addr, _zone_name, z, self.device_id)) #v2.2.0, updated to add node to queue, rather that adding to ISY immediately
        except Exception as ex:
            _success = False
            LOGGER.error('Error discovering and adding Zones on Rachio Controller %s (%s): %s', self.name, self.address, str(ex))
        
        try:
            _schedules = self.device['scheduleRules']
            LOGGER.info('%i Rachio schedules found on "%s" controller. Adding to ISY', len(_schedules), self.name)
            for s in _schedules:
                _sched_id = str(s['id'])
                _sched_addr = self.address + _sched_id[-2:] #construct address for this schedule (mac address of controller appended with last 2 characters of schedule unique id) because ISY limit is 14 characters
                _sched_name = str(s['name'])
                if _sched_addr not in self.parent.nodes:
                    #LOGGER.info('Adding new Rachio Schedule to %s Controller, %s(%s)', self.name, _sched_name, _sched_addr)
                    self.parent.addNodeQueue(RachioSchedule(self.parent, self.address, _sched_addr, _sched_name, s, self.device_id)) #v2.2.0, updated to add node to queue, rather that adding to ISY immediately
        except Exception as ex:
            _success = False
            LOGGER.error('Error discovering and adding Schedules on Rachio Controller %s (%s): %s', self.name, self.address, str(ex))

        try:
            _flex_schedules = self.device['flexScheduleRules']
            LOGGER.info('%i Rachio Flex schedules found on "%s" controller. Adding to ISY', len(_flex_schedules), self.name)
            for f in _flex_schedules:
                _flex_sched_id = str(f['id'])
                _flex_sched_addr = self.address + _flex_sched_id[-2:] #construct address for this schedule (mac address of controller appended with last 2 characters of schedule unique id) because ISY limit is 14 characters
                _flex_sched_name = str(f['name'])
                if _flex_sched_addr not in self.parent.nodes:
                    #LOGGER.info('Adding new Rachio Flex Schedule to %s Controller, %s(%s)',self.name, _flex_sched_name, _flex_sched_addr)
                    self.parent.addNodeQueue(RachioFlexSchedule(self.parent, self.address, _flex_sched_addr, _flex_sched_name, f, self.device_id)) #v2.2.0, updated to add node to queue, rather that adding to ISY immediately
        except Exception as ex:
            _success = False
            LOGGER.error('Error discovering and adding Flex Schedules on Rachio Controller %s (%s): %s', self.name, self.address, str(ex))

        return _success

    def update_info(self, force=False):
        _running = False #initialize variable so that it could be used even if there was not a need to update the running status of the controller
        try:
            #Get latest device info and populate drivers
            _device = self.parent.r_api.device.get(self.device_id)[1]
            self.device = _device
            
            _currentSchedule = self.parent.r_api.device.getCurrentSchedule(self.device_id)[1]
            if self.currentSchedule == []: self.currentSchedule = _currentSchedule

        except Exception as ex:
            LOGGER.error('Connection Error on %s Rachio Controller refreshState. This could mean an issue with internet connectivity or Rachio servers, normally safe to ignore. %s', self.name, str(ex))
            return False
            
        # ST -> Status (whether Rachio is running a schedule or not)
        try:
            if 'status' in _currentSchedule and 'status' in self.currentSchedule:
                if (_currentSchedule['status'] != self.currentSchedule['status']):
                    _running = (str(_currentSchedule['status']) == "PROCESSING")
                    self.setDriver('ST',(0,100)[_running])
            elif 'status' in _currentSchedule: #There was no schedule last time we checked but there is now, update ISY:
                _running = (str(_currentSchedule['status']) == "PROCESSING")
                self.setDriver('ST',(0,100)[_running])
            elif 'status' in self.currentSchedule: #there was a schedule last time but there isn't now, update ISY:
                self.setDriver('ST',0)
            else:
                self.setDriver('ST',0)
        except Exception as ex:
            LOGGER.error('Error updating current schedule running status on %s Rachio Controller. %s', self.name, str(ex))

        # GV0 -> "Connected"
        try:
            if force or (_device['status'] != self.device['status']):
                _connected = (_device['status'] == "ONLINE")
                self.setDriver('GV0',int(_connected))
        except Exception as ex:
            self.setDriver('GV0',0)
            LOGGER.error('Error updating connection status on %s Rachio Controller. %s', self.name, str(ex))

        # GV1 -> "Enabled"
        try:
            if force or (_device['on'] != self.device['on']):
                self.setDriver('GV1',int(_device['on']))
        except Exception as ex:
            self.setDriver('GV1',0)
            LOGGER.error('Error updating status on %s Rachio Controller. %s', self.name, str(ex))

        # GV2 -> "Paused"
        try:
            if force or (_device['paused'] != self.device['paused']):
                self.setDriver('GV2', int(_device['paused']))
        except Exception as ex:
            LOGGER.error('Error updating paused status on %s Rachio Controller. %s', self.name, str(ex))

        # GV3 -> "Rain Delay Remaining" in Minutes
        try:
            if 'rainDelayExpirationDate' in _device: 
                _current_time = int(time.time())
                _rainDelayExpiration = _device['rainDelayExpirationDate'] / 1000.
                _rainDelay_minutes_remaining = int(max(_rainDelayExpiration - _current_time,0) / 60.)
                if force or (_rainDelay_minutes_remaining != self.rainDelay_minutes_remaining):
                    self.setDriver('GV3', _rainDelay_minutes_remaining)
                    self.rainDelay_minutes_remaining = _rainDelay_minutes_remaining
            elif force: self.setDriver('GV3', 0)
        except Exception as ex:
            LOGGER.error('Error updating remaining rain delay duration on %s Rachio Controller. %s', self.name, str(ex))
        
        # GV10 -> Active Run Type
        try:
            if 'type' in _currentSchedule: # True when a schedule is running
                _runType = _currentSchedule['type']
                _runVal = 3 #default to "OTHER"
                for key in self.runTypes:
                    if self.runTypes[key].lower() == _runType.lower():
                        _runVal = key
                        break
                self.setDriver('GV10', _runVal)
            else: 
                self.setDriver('GV10', 0, report=force)
        except Exception as ex:
            LOGGER.error('Error updating active run type on %s Rachio Controller. %s', self.name, str(ex))

        # GV4 -> Active Zone #
        if 'zoneId' in _currentSchedule and  'zoneId' in self.currentSchedule:
            if force or (_currentSchedule['zoneId'] != self.currentSchedule['zoneId']):
                try:
                    _active_zone = self.parent.r_api.zone.get(_currentSchedule['zoneId'])[1]
                    self.setDriver('GV4',_active_zone['zoneNumber'])
                except Exception as ex:
                    LOGGER.error('Error updating active zone on %s Rachio Controller. %s', self.name, str(ex))
        elif 'zoneId' in self.currentSchedule: #there was a zone but now there's not, that must mean we're no longer watering and there's therefore no current zone #
            self.setDriver('GV4',0)
        elif 'zoneId' in _currentSchedule: #there's a zone now but there wasn't before, we can try to find the new zone #
            try:
                _active_zone = self.parent.r_api.zone.get(_currentSchedule['zoneId'])[1]
                self.setDriver('GV4',_active_zone['zoneNumber'])
            except Exception as ex:
                LOGGER.error('Error updating new zone on %s Rachio Controller. %s', self.name, str(ex))
        else: #no schedule running:
            if force: self.setDriver('GV4',0)
        
        # GV5 -> Active Schedule remaining minutes and GV6 -> Active Schedule minutes elapsed
        try:
            if 'startDate' in _currentSchedule and 'duration' in _currentSchedule:
                _current_time = int(time.time())
                _start_time = int(_currentSchedule['startDate'] / 1000)
                _duration = int(_currentSchedule['duration'])

                _seconds_elapsed = max(_current_time - _start_time,0)
                _minutes_elapsed = round(_seconds_elapsed / 60. ,1)
                
                _seconds_remaining = max(_duration - _seconds_elapsed,0)
                _minutes_remaining = round(_seconds_remaining / 60. ,1)

                self.setDriver('GV5',_minutes_remaining)
                self.setDriver('GV6',_minutes_elapsed)
                #LOGGER.info('%f minutes elapsed and %f minutes remaining on %s Rachio Controller. %s', _minutes_elapsed, _minutes_remaining, self.name)
            else: 
                self.setDriver('GV5',0.0)
                self.setDriver('GV6',0.0)
        except Exception as ex:
            LOGGER.error('Error trying to retrieve active schedule minutes remaining/elapsed on %s Rachio Controller. %s', self.name, str(ex))

        # GV7 -> Cycling (true/false)
        try:
            if 'cycling' in _currentSchedule and 'cycling' in self.currentSchedule:
                if force or (_currentSchedule['cycling'] != self.currentSchedule['cycling']):
                    self.setDriver('GV7',int(_currentSchedule['cycling']))
            elif 'cycling' in _currentSchedule: #there's a schedule running now, but there wasn't last time we checked, update the ISY:
                self.setDriver('GV7',int(_currentSchedule['cycling']))
            elif force: self.setDriver('GV7', 0) #no schedule active
        except Exception as ex:
            LOGGER.error('Error trying to retrieve cycling status on %s Rachio Controller. %s', self.name, str(ex))
        
        # GV8 -> Cycle Count
        try:
            if 'cycleCount' in _currentSchedule and 'cycleCount' in self.currentSchedule:
                if force or (_currentSchedule['cycleCount'] != self.currentSchedule['cycleCount']):
                    self.setDriver('GV8',_currentSchedule['cycleCount'])
            elif 'cycleCount' in _currentSchedule: #there's a schedule running now, but there wasn't last time we checked, update the ISY:
                self.setDriver('GV8',_currentSchedule['cycleCount'])
            elif force: self.setDriver('GV8',0) #no schedule active
        except Exception as ex:
            LOGGER.error('Error trying to retrieve cycle count on %s Rachio Controller. %s', self.name, str(ex))

        # GV9 -> Total Cycle Count
        try:
            if 'totalCycleCount' in _currentSchedule and 'totalCycleCount' in self.currentSchedule:
                if force or (_currentSchedule['totalCycleCount'] != self.currentSchedule['totalCycleCount']):
                    self.setDriver('GV9',_currentSchedule['totalCycleCount'])
            elif 'totalCycleCount' in _currentSchedule: #there's a schedule running now, but there wasn't last time we checked, update the ISY:
                self.setDriver('GV9',_currentSchedule['totalCycleCount'])
            elif force: self.setDriver('GV9',0) #no schedule active
        except Exception as ex:
            LOGGER.error('Error trying to retrieve total cycle count on %s Rachio Controller. %s', self.name, str(ex))

        # GV11 -> Minutes until next automatic schedule start
        # GV12 -> Type of next schedule (FLEX, or FIXED)
        try:
            _scheduleItems = self.parent.r_api.device.getScheduleItem(self.device_id)[1]
            if force or self.scheduleItems == []: self.scheduleItems = _scheduleItems
            if len(_scheduleItems) > 0:
                _current_time = int(time.time())
                _next_start_time = int(_scheduleItems[0]['absoluteStartDate'] / 1000.) #TODO: Looks like earliest schedule is always in the 0th element, but might need to actually loop through and check.
                _seconds_remaining = max(_next_start_time - _current_time,0)
                _minutes_remaining = round(_seconds_remaining / 60. ,1)
                self.setDriver('GV11',_minutes_remaining)

                _scheduleType = _scheduleItems[0]['scheduleType']
                _scheduleVal = 3 #default to "OTHER" in case an unexpected item is returned (API documentation does not include exhaustive list of possibilities)
                for key in self.scheduleTypes:
                    if self.scheduleTypes[key].lower() == _scheduleType.lower():
                        _scheduleVal = key
                        break
                self.setDriver('GV12',_scheduleVal)
            elif force: 
                self.setDriver('GV11',0.0)
                self.setDriver('GV12',0)
        except Exception as ex:
            LOGGER.error('Error trying to retrieve minutes remaining/type of next planned schedule on %s Rachio Controller. %s', self.name, str(ex))
        
        self.device = _device
        self.currentSchedule = _currentSchedule
        #if force: self.reportDrivers() Removed v2.2.0
        return True

    def query(self, command = None):
        LOGGER.info('query command received on %s Rachio Controller.', self.name)
        self.update_info(force=True)
        return True

    def enable(self, command): #Enables Rachio (schedules, weather intelligence, water budget, etc...)
        self._tries = 0
        while self._tries < 2: #TODO: the first command to the Rachio server fails frequently for some reason with an SSL WRONG_VERSION_NUMBER error.  This is a temporary workaround to try a couple of times before giving up
            try:
                self.parent.r_api.device.on(self.device_id)
                self.update_info(force=False) #update info but don't force updates to ISY if values haven't changed.
                LOGGER.info('Command received to enable %s Controller',self.name)
                self._tries = 0
                return True
            except Exception as ex:
                LOGGER.error('Error turning on %s. %s', self.name, str(ex))
                self._tries = self._tries + 1
        return False

    def disable(self, command): #Disables Rachio (schedules, weather intelligence, water budget, etc...)
        self._tries = 0
        while self._tries < 2: #TODO: the first command to the Rachio server fails frequently for some reason with an SSL WRONG_VERSION_NUMBER error.  This is a temporary workaround to try a couple of times before giving up
            try:
                self.parent.r_api.device.off(self.device_id)
                self.update_info(force=False) #update info but don't force updates to ISY if values haven't changed.
                LOGGER.info('Command received to disable %s Controller',self.name)
                self._tries = 0
                return True
            except Exception as ex:
                LOGGER.error('Error turning off %s. %s', self.name, str(ex))
                self._tries = self._tries + 1
        return False

    def stopCmd(self, command):
        self._tries = 0
        while self._tries < 2: #TODO: the first command to the Rachio server fails frequently for some reason with an SSL WRONG_VERSION_NUMBER error.  This is a temporary workaround to try a couple of times before giving up
            try:
                self.parent.r_api.device.stopWater(self.device_id)
                LOGGER.info('Command received to stop watering on %s Controller',self.name)
                self.update_info(force=False) #update info but don't force updates to ISY if values haven't changed.
                self._tries = 0
                return True
            except Exception as ex:
                LOGGER.error('Error stopping watering on %s. %s', self.name, str(ex))
                self._tries = self._tries + 1
        return False
    
    def rainDelay(self, command):
        _minutes = command.get('value')
        if _minutes is None:
            LOGGER.error('Rain Delay requested on %s Rachio Controller but no duration specified', self.name)
            return False
        else:
            self._tries = 0
            while self._tries < 2: #TODO: the first command to the Rachio server fails frequently for some reason with an SSL WRONG_VERSION_NUMBER error.  This is a temporary workaround to try a couple of times before giving up
                try:
                    _seconds = int(_minutes * 60.)
                    self.parent.r_api.device.rainDelay(self.device_id, _seconds)
                    self.update_info(force=False) #update info but don't force updates to ISY if values haven't changed.
                    LOGGER.info('Received rain Delay command on %s Rachio Controller for %s minutes', self.name, str(_minutes))
                    self._tries = 0
                    return True
                except Exception as ex:
                    LOGGER.error('Error setting rain delay on %s Rachio Controller to _seconds %i (%s)', self.name, _seconds, str(ex))
                    self._tries = self._tries +1
            return False

    drivers = [{'driver': 'ST', 'value': 0, 'uom': 78}, #Status (On/Off)
               {'driver': 'GV0', 'value': 0, 'uom': 2}, #Connected (True/False)
               {'driver': 'GV1', 'value': 0, 'uom': 2}, #Enabled (True/False)
               {'driver': 'GV2', 'value': 0, 'uom': 2}, #Paused (True/False)
               {'driver': 'GV3', 'value': 0, 'uom': 45}, #Rain Delay Minutes Remaining (Minutes)
               {'driver': 'GV4', 'value': 0, 'uom': 56}, #Active Zone # (Raw Value)
               {'driver': 'GV5', 'value': 0, 'uom': 45}, #Active Schedule Minutes Remaining (Minutes)
               {'driver': 'GV6', 'value': 0, 'uom': 45}, #Active Schedule Minutes Elapsed (Minutes)
               {'driver': 'GV7', 'value': 0, 'uom': 2}, #Cycling (True/False)
               {'driver': 'GV8', 'value': 0, 'uom': 56}, #Cycle Count (Raw Value)
               {'driver': 'GV9', 'value': 0, 'uom': 56}, #Total Cycle Count (Raw Value)
               {'driver': 'GV10', 'value': 0, 'uom': 25}, #Current Schedule Type (Enumeration)
               {'driver': 'GV11', 'value': 0, 'uom': 45}, #Minutes until next automatic schedule start (Minutes)
               {'driver': 'GV12', 'value': 0, 'uom': 25} #Type of next schedule (Enumeration)
               ]

    id = 'rachio_device'
    commands = {'DON': enable, 'DOF': disable, 'QUERY': query, 'STOP': stopCmd, 'RAIN_DELAY': rainDelay}

class RachioZone(polyinterface.Node):
    def __init__(self, parent, primary, address, name, zone, device_id):
        super().__init__(parent, primary, address, name)
        self.device_id = device_id
        self.zone = zone
        self.zone_id = zone['id']
        self.name = name
        self.address = address
        self.rainDelayExpiration = 0
        self.currentSchedule = []
        self._tries = 0

    def start(self):
        self.update_info()

    def discover(self, command=None):
        # No discovery needed (no nodes are subordinate to Zones)
        pass

    def update_info(self, force=False): #setting "force" to "true" updates drivers even if the value hasn't changed
        _running = False #initialize variable so that it could be used even if there was not a need to update the running status of the zone
        LOGGER.debug('Updating info for zone %s with id %s, force=%s',self.address, str(self.zone_id), str(force))
        try:
            #Get latest zone info and populate drivers
            _zone = self.parent.r_api.zone.get(self.zone_id)[1]
            if force: self.zone = _zone
            _currentSchedule = self.parent.r_api.device.getCurrentSchedule(self.device_id)[1]
            if self.currentSchedule == []: self.currentSchedule = _currentSchedule
        except Exception as ex:
            LOGGER.error('Connection Error on %s Rachio zone. This could mean an issue with internet connectivity or Rachio servers, normally safe to ignore. %s', self.name, str(ex))
            return False
            
        # ST -> Status (whether Rachio zone is running a schedule or not)
        try:
            if 'status' in _currentSchedule and 'zoneId' in _currentSchedule and 'status' in self.currentSchedule and 'zoneId' in self.currentSchedule:
                if force or (_currentSchedule['status'] != self.currentSchedule['status']) or (_currentSchedule['zoneId'] != self.currentSchedule['zoneId']):
                    _running = (str(_currentSchedule['status']) == "PROCESSING") and (_currentSchedule['zoneId'] == self.zone_id)
                    self.setDriver('ST',(0,100)[_running])
            elif 'status' in _currentSchedule and 'zoneId' in _currentSchedule: #there's a schedule running now, but there wasn't last time we checked, update the ISY:
                _running = (str(_currentSchedule['status']) == "PROCESSING") and (_currentSchedule['zoneId'] == self.zone_id)
                self.setDriver('ST',(0,100)[_running])
            elif 'status' in self.currentSchedule and 'zoneId' in self.currentSchedule: #schedule stopped running since last time, update the ISY:
                self.setDriver('ST',0)
            elif force:
                self.setDriver('ST',0)
        except Exception as ex:
            LOGGER.error('Error updating current schedule running status on %s Rachio Zone. %s', self.name, str(ex))

        # GV0 -> "Enabled"
        try:
            if force or (_zone['enabled'] != self.zone['enabled']):
                self.setDriver('GV0',int(_zone['enabled']))
        except Exception as ex:
            self.setDriver('GV0',0)
            LOGGER.error('Error updating enable status on %s Rachio Zone. %s', self.name, str(ex))

        # GV1 -> "Zone Number"
        try:
            if force or (_zone['zoneNumber'] != self.zone['zoneNumber']):
                self.setDriver('GV1', _zone['zoneNumber'])
        except Exception as ex:
            LOGGER.error('Error updating zone number on %s Rachio Zone. %s', self.name, str(ex))

        # GV2 -> Available Water
        # TODO: Not 100% sure what this is or if the units are correct, need to see if Rachio has any additional info
        try:
            if force or (_zone['availableWater'] != self.zone['availableWater']):
                self.setDriver('GV2', _zone['availableWater'])
        except Exception as ex:
            LOGGER.error('Error updating available water on %s Rachio Zone. %s', self.name, str(ex))

        # GV3 -> root zone depth
        # TODO: Not 100% sure what this is or if the units are correct, need to see if Rachio has any additional info
        try:
            if force or (_zone['rootZoneDepth'] != self.zone['rootZoneDepth']):
                self.setDriver('GV3', _zone['rootZoneDepth'])
        except Exception as ex:
            LOGGER.error('Error updating root zone depth on %s Rachio Zone. %s', self.name, str(ex))

		# GV4 -> allowed depletion
        # TODO: Not 100% sure what this is or if the units are correct, need to see if Rachio has any additional info
        try:
            if force or (_zone['managementAllowedDepletion'] != self.zone['managementAllowedDepletion']):
                self.setDriver('GV4', _zone['managementAllowedDepletion'])
        except Exception as ex:
            LOGGER.error('Error updating allowed depletion on %s Rachio Zone. %s', self.name, str(ex))

		# GV5 -> efficiency
        try:
            if force or (_zone['efficiency'] != self.zone['efficiency']):
                self.setDriver('GV5', int(_zone['efficiency'] * 100.))
        except Exception as ex:
            LOGGER.error('Error updating efficiency on %s Rachio Zone. %s', self.name, str(ex))

		# GV6 -> square feet
        # TODO: This is in square feet, but there's no unit available in the ISY for square feet.  Update if UDI makes it available
        try:
            if force or (_zone['yardAreaSquareFeet'] != self.zone['yardAreaSquareFeet']):
                self.setDriver('GV6', _zone['yardAreaSquareFeet'])
        except Exception as ex:
            LOGGER.error('Error updating square footage on %s Rachio Zone. %s', self.name, str(ex))

		# GV7 -> irrigation amount
        # TODO: Not 100% sure what this is or if the units are correct, need to see if Rachio has any additional info
        try:
            if 'irrigationAmount' in _zone and 'irrigationAmount' in self.zone['irrigationAmount']:
                if force or (_zone['irrigationAmount'] != self.zone['irrigationAmount']):
                    self.setDriver('GV7', _zone['irrigationAmount'])
            else:
                if force: self.setDriver('GV7', 0)
        except Exception as ex:
            LOGGER.error('Error updating irrigation amount on %s Rachio Zone. %s', self.name, str(ex))

		# GV8 -> depth of water
        # TODO: Not 100% sure what this is or if the units are correct, need to see if Rachio has any additional info
        try:
            if force or (_zone['depthOfWater'] != self.zone['depthOfWater']):
                self.setDriver('GV8', _zone['depthOfWater'])
        except Exception as ex:
            LOGGER.error('Error updating depth of water on %s Rachio Zone. %s', self.name, str(ex))

		# GV9 -> runtime
        # TODO: Not 100% sure what this is or if the units are correct, need to see if Rachio has any additional info
        try:
            if force or (_zone['runtime'] != self.zone['runtime']):
                self.setDriver('GV9', _zone['runtime'])
        except Exception as ex:
            LOGGER.error('Error updating runtime on %s Rachio Zone. %s', self.name, str(ex))

		# GV10 -> inches per hour
        try:
            if force or (_zone['customNozzle']['inchesPerHour'] != self.zone['customNozzle']['inchesPerHour']):
                self.setDriver('GV10', _zone['customNozzle']['inchesPerHour'])
        except Exception as ex:
            LOGGER.error('Error updating inches per hour on %s Rachio Zone. %s', self.name, str(ex))
        
        self.zone = _zone
        self.currentSchedule = _currentSchedule
        #if force: self.reportDrivers() Removed v2.2.0
        return True

    def query(self, command = None):
        LOGGER.info('query command received on %s Rachio Zone', self.name)
        self.update_info(force=True)
        return True

    def startCmd(self, command):
        _minutes = command.get('value')
        if _minutes is None:
            LOGGER.error('Zone %s requested to start but no duration specified', self.name)
            return False
        else:
            self._tries = 0
            while self._tries < 2: #TODO: the first command to the Rachio server fails frequently for some reason with an SSL WRONG_VERSION_NUMBER error.  This is a temporary workaround to try a couple of times before giving up
                try:
                    if _minutes == 0:
                        LOGGER.error('Zone %s requested to start but duration specified was zero', self.name)
                        return False
                    _seconds = int(_minutes * 60.)
                    self.parent.r_api.zone.start(self.zone_id, _seconds)
                    LOGGER.info('Command received to start watering zone %s for %i minutes',self.name, _minutes)
                    self.update_info(force=False) #update info but don't force updates to ISY if values haven't changed.
                    self._tries = 0
                    return True
                except Exception as ex:
                    LOGGER.error('Error starting watering on zone %s. %s', self.name, str(ex))
                    self._tries = self._tries + 1
            return False

    drivers = [{'driver': 'ST', 'value': 0, 'uom': 78}, #Running (On/Off)
               {'driver': 'GV0', 'value': 0, 'uom': 2}, #Enabled (True/False)
               {'driver': 'GV1', 'value': 0, 'uom': 56}, #Zone Number (Raw Value)
               {'driver': 'GV2', 'value': 0, 'uom': 105}, #Available Water (Inches)
               {'driver': 'GV3', 'value': 0, 'uom': 105}, #Root Zone Depth (Inches)
               {'driver': 'GV4', 'value': 0, 'uom': 105}, #Allowed Depletion (Inches)
               {'driver': 'GV5', 'value': 0, 'uom': 51}, #Efficiency (Percent)
               {'driver': 'GV6', 'value': 0, 'uom': 18}, #Zone Area (*Square* Feet)
               {'driver': 'GV7', 'value': 0, 'uom': 105}, #Irrigation Amount (Inches)
               {'driver': 'GV8', 'value': 0, 'uom': 105}, #Depth of Water (Inches)
               {'driver': 'GV9', 'value': 0, 'uom': 45}, #Runtime (Minutes)
               {'driver': 'GV10', 'value': 0, 'uom': 24} #Inches per Hour
               ]

    id = 'rachio_zone'
    commands = {'QUERY': query, 'START': startCmd}

class RachioSchedule(polyinterface.Node):
    def __init__(self, parent, primary, address, name, schedule, device_id):
        super().__init__(parent, primary, address, name)
        self.device_id = device_id
        self.schedule = schedule
        self.schedule_id = schedule['id']
        self.name = name
        self.address = address
        self.currentSchedule = []
        self.scheduleItems = []
        self._tries = 0

    def start(self):
        self.update_info()

    def discover(self, command=None):
        # No discovery needed (no nodes are subordinate to Schedules)
        pass
        
    def update_info(self, force=False): #setting "force" to "true" updates drivers even if the value hasn't changed
        _running = False #initialize variable so that it could be used even if there was not a need to update the running status of the schedule
        try:
            #Get latest schedule info and populate drivers
            _schedule = self.parent.r_api.schedulerule.get(self.schedule_id)[1]
            if force: self.schedule = _schedule
            _currentSchedule = self.parent.r_api.device.getCurrentSchedule(self.device_id)[1]
            if self.currentSchedule == []: self.currentSchedule = _currentSchedule
        except Exception as ex:
            LOGGER.error('Connection Error on %s Rachio schedule. This could mean an issue with internet connectivity or Rachio servers, normally safe to ignore. %s', self.name, str(ex))
            return False
            
        # ST -> Status (whether Rachio schedule is running a schedule or not)
        try:
            if 'scheduleRuleId' in _currentSchedule and 'scheduleRuleId' in self.currentSchedule:
                if force or (_currentSchedule['scheduleRuleId'] != self.currentSchedule['scheduleRuleId']):
                    _running = (_currentSchedule['scheduleRuleId'] == self.schedule_id)
                    self.setDriver('ST',(0,100)[_running])
            elif 'scheduleRuleId' in _currentSchedule: #There was no schedule last time we checked but there is now, update ISY:
                _running = (str(_currentSchedule['scheduleRuleId']) == self.schedule_id)
                self.setDriver('ST',(0,100)[_running])
            elif 'scheduleRuleId' in self.currentSchedule: #there was a schedule last time but there isn't now, update ISY:
                self.setDriver('ST',0)
            elif force:
                self.setDriver('ST',0)
        except Exception as ex:
            LOGGER.error('Error updating current schedule running status on %s Rachio Schedule. %s', self.name, str(ex))

        # GV0 -> "Enabled"
        try:
            if force or (_schedule['enabled'] != self.schedule['enabled']):
                self.setDriver('GV0',int(_schedule['enabled']))
        except Exception as ex:
            LOGGER.error('Error updating enable status on %s Rachio Schedule. %s', self.name, str(ex))

        # GV1 -> "rainDelay" status
        try:
            if force or (_schedule['rainDelay'] != self.schedule['rainDelay']):
                self.setDriver('GV1',int(_schedule['rainDelay']))
        except Exception as ex:
            LOGGER.error('Error updating schedule rain delay on %s Rachio Schedule. %s', self.name, str(ex))

        # GV2 -> duration (minutes)
        try:
            if force or (_schedule['totalDuration'] != self.schedule['totalDuration']):
                self.setDriver('GV2', _schedule['totalDuration'])
        except Exception as ex:
            LOGGER.error('Error updating total duration on %s Rachio Schedule. %s', self.name, str(ex))

        # GV3 -> seasonal adjustment
        try:
            if force or (_schedule['seasonalAdjustment'] != self.schedule['seasonalAdjustment']):
                _seasonalAdjustment = _schedule['seasonalAdjustment'] * 100
                self.setDriver('GV3', _seasonalAdjustment)
        except Exception as ex:
            LOGGER.error('Error updating seasonal adjustment on %s Rachio Schedule. %s', self.name, str(ex))

        # GV4 -> Minutes until next automatic schedule start
        try:
            _scheduleItems = self.parent.r_api.device.getScheduleItem(self.device_id)[1]
            if force or self.scheduleItems == []: self.scheduleItems = _scheduleItems
            if len(_scheduleItems) > 0:
                _current_time = int(time.time())
                _next_start_time = 0
                for _item in _scheduleItems: #find the lowest planned start time for this schedule:
                    if _item['scheduleRuleId'] == self.schedule_id:
                        if _next_start_time == 0 or _item['absoluteStartDate'] < _next_start_time:
                            _next_start_time = _item['absoluteStartDate']
                
                _next_start_time = int(_next_start_time / 1000.)
                _seconds_remaining = max(_next_start_time - _current_time,0)
                _minutes_remaining = round(_seconds_remaining / 60. ,1)
                self.setDriver('GV4',_minutes_remaining)

            elif force: 
                self.setDriver('GV4',0.0)
        except Exception as ex:
            LOGGER.error('Error trying to retrieve minutes remaining until next run of %s Rachio Schedule. %s', self.name, str(ex))

        self.schedule = _schedule
        self.currentSchedule = _currentSchedule
        #if force: self.reportDrivers() Removed v2.2.0
        return True
        
    def query(self, command = None):
        LOGGER.info('query command received on %s Rachio Schedule.', self.name)
        self.update_info(force=True)
        return True

    def startCmd(self, command):
        self._tries = 0
        while self._tries < 2: #TODO: the first command to the Rachio server fails frequently for some reason with an SSL WRONG_VERSION_NUMBER error.  This is a temporary workaround to try a couple of times before giving up
            try:
                self.parent.r_api.schedulerule.start(self.schedule_id)
                LOGGER.info('Command received to start watering schedule %s',self.name)
                self.update_info(force=False) #update info but don't force updates to ISY if values haven't changed.
                self._tries = 0
                return True
            except Exception as ex:
                LOGGER.error('Error starting watering on schedule %s. %s', self.name, str(ex))
                self._tries = self._tries + 1
        return False
    
    def skip(self, command):
        self._tries = 0
        while self._tries < 2: #TODO: the first command to the Rachio server fails frequently for some reason with an SSL WRONG_VERSION_NUMBER error.  This is a temporary workaround to try a couple of times before giving up
            try:
                self.parent.r_api.schedulerule.skip(self.schedule_id)
                LOGGER.info('Command received to skip watering schedule %s',self.name)
                self.update_info(force=False) #update info but don't force updates to ISY if values haven't changed.
                self._tries = 0
                return True
            except Exception as ex:
                LOGGER.error('Error skipping watering on schedule %s. %s', self.name, str(ex))
                self._tries = self._tries = 1
        return False

    def seasonalAdjustment(self, command):
        self._tries = 0
        while self._tries < 2: #TODO: the first command to the Rachio server fails frequently for some reason with an SSL WRONG_VERSION_NUMBER error.  This is a temporary workaround to try a couple of times before giving up
            try:
                _value = command.get('value')
                if _value is not None:
                    _value = _value / 100.
                    self.parent.r_api.schedulerule.seasonalAdjustment(self.schedule_id, _value)
                    LOGGER.info('Command received to change seasonal adjustment on schedule %s to %s',self.name, str(_value))
                    self.update_info(force=False) #update info but don't force updates to ISY if values haven't changed.
                    self._tries = 0
                    return True
                else:
                    LOGGER.error('Command received to change seasonal adjustment on schedule %s but no value supplied',self.name)
                    return False
            except Exception as ex:
                LOGGER.error('Error changing seasonal adjustment on schedule %s. %s', self.name, str(ex))
                self._tries = self._tries + 1
        return False

    drivers = [{'driver': 'ST', 'value': 0, 'uom': 78}, #Running (On/Off)
               {'driver': 'GV0', 'value': 0, 'uom': 2}, #Enabled (True/False)
               {'driver': 'GV1', 'value': 0, 'uom': 2}, #Rain Delay (True/False)
               {'driver': 'GV2', 'value': 0, 'uom': 45}, #Duration (Minutes)
               {'driver': 'GV3', 'value': 0, 'uom': 51}, #Seasonal Adjustment (Percent)
               {'driver': 'GV4', 'value': 0, 'uom': 45} #Time until next Schedule Start (Minutes)
               ]

    id = 'rachio_schedule'
    commands = {'QUERY': query, 'START': startCmd, 'SKIP':skip, 'ADJUST':seasonalAdjustment}

class RachioFlexSchedule(polyinterface.Node):
    def __init__(self, parent, primary, address, name, schedule, device_id):
        super().__init__(parent, primary, address, name)
        self.device_id = device_id
        self.schedule = schedule
        self.schedule_id = schedule['id']
        self.name = name
        self.address = address
        self.currentSchedule = []
        self._tries = 0

    def start(self):
        self.update_info()

    def discover(self, command=None):
        # No discovery needed (no nodes are subordinate to Flex Schedules)
        pass

    def update_info(self, force=False): #setting "force" to "true" updates drivers even if the value hasn't changed
        _running = False #initialize variable so that it could be used even if there was not a need to update the running status of the schedule
        try:
            #Get latest schedule info and populate drivers
            _schedule = self.parent.r_api.flexschedulerule.get(self.schedule_id)[1]
            if force: self.schedule = _schedule
            _currentSchedule = self.parent.r_api.device.getCurrentSchedule(self.device_id)[1]
            if self.currentSchedule == []: self.currentSchedule = _currentSchedule
        except Exception as ex:
            LOGGER.error('Connection Error on %s Rachio schedule. This could mean an issue with internet connectivity or Rachio servers, normally safe to ignore. %s', self.name, str(ex))
            return False
            
        # ST -> Status (whether Rachio schedule is running a schedule or not)
        try:
            if 'scheduleRuleId' in _currentSchedule and 'scheduleRuleId' in self.currentSchedule:
                if force or (_currentSchedule['scheduleRuleId'] != self.currentSchedule['scheduleRuleId']):
                    _running = (_currentSchedule['scheduleRuleId'] == self.schedule_id)
                    self.setDriver('ST',(0,100)[_running])
            elif 'scheduleRuleId' in _currentSchedule: #There was no schedule last time we checked but there is now, update ISY:
                _running = (str(_currentSchedule['scheduleRuleId']) == self.schedule_id)
                self.setDriver('ST',(0,100)[_running])
            elif 'scheduleRuleId' in self.currentSchedule: #there was a schedule last time but there isn't now, update ISY:
                self.setDriver('ST',0)
            elif force:
                self.setDriver('ST',0)
        except Exception as ex:
            LOGGER.error('Error updating current schedule running status on %s Rachio FlexSchedule. %s', self.name, str(ex))

        # GV0 -> "Enabled"
        try:
            if force or (_schedule['enabled'] != self.schedule['enabled']):
                self.setDriver('GV0',int(_schedule['enabled']))
        except Exception as ex:
            LOGGER.error('Error updating enable status on %s Rachio FlexSchedule. %s', self.name, str(ex))

        # GV2 -> duration (minutes)
        try:
            if force or (_schedule['totalDuration'] != self.schedule['totalDuration']):
                _seconds = _schedule['totalDuration']
                _minutes = int(_seconds / 60.)
                self.setDriver('GV2', _minutes)
        except Exception as ex:
            LOGGER.error('Error updating total duration on %s Rachio FlexSchedule. %s', self.name, str(ex))

        self.schedule = _schedule
        self.currentSchedule = _currentSchedule
        #self.reportDrivers() Removed v2.2.0
        return True

        # GV4 -> Minutes until next automatic schedule start
        try:
            _scheduleItems = self.parent.r_api.device.getScheduleItem(self.device_id)[1]
            if force or self.scheduleItems == []: self.scheduleItems = _scheduleItems
            if len(_scheduleItems) > 0:
                _current_time = int(time.time())
                _next_start_time = 0
                for _item in _scheduleItems: #find the lowest planned start time for this schedule:
                    if _item['scheduleRuleId'] == self.schedule_id:
                        if _next_start_time == 0 or _item['absoluteStartDate'] < _next_start_time:
                            _next_start_time = _item['absoluteStartDate']
                
                _next_start_time = int(_next_start_time / 1000.)
                _seconds_remaining = max(_next_start_time - _current_time,0)
                _minutes_remaining = round(_seconds_remaining / 60. ,1)
                self.setDriver('GV4',_minutes_remaining)

            elif force: 
                self.setDriver('GV4',0.0)
        except Exception as ex:
            LOGGER.error('Error trying to retrieve minutes remaining until next run of %s Rachio FlexSchedule. %s', self.name, str(ex))
        
        #if force: self.reportDrivers() Removed v2.2.0

    def query(self, command = None):
        LOGGER.info('query command received on %s Rachio Flex Schedule', self.name)
        self.update_info(force=True)
        return True

    drivers = [{'driver': 'ST', 'value': 0, 'uom': 78}, #Running (On/Off)
               {'driver': 'GV0', 'value': 0, 'uom': 2}, #Enabled (True/False)
               {'driver': 'GV2', 'value': 0, 'uom': 45} #Duration (Minutes)
               ]

    id = 'rachio_flexschedule'
    commands = {'QUERY': query}

if __name__ == "__main__":
    try:
        polyglot = polyinterface.Interface('Rachio')
        polyglot.start()
        control = Controller(polyglot)
        control.runForever()
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
