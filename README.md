# Rachio-polyglot
This is the Rachio Node Server for the ISY Polyglot V2 interface.  
(c) fahrer16 aka Brian Feeney.  
MIT license. 

The Rachio water controller uses a cloud-based API that is documented here: https://rachio.readme.io/docs/getting-started.
This node server currently implements the Person, Device, and Zone leaves of the Rachio api.


# Installation Instructions:
1. Backup ISY (just in case)
2. Clone the Rachio Node Server into the /.polyglot/nodeservers folder for the user that runs polyglot v2:
`Assuming you're logged in as the user that runs polyglot, cd cd ~/.polyglot/nodeservers
`git clone https://github.com/fahrer16/udi-rachio-poly.git
3. Install pre-requisites using install.sh script
  * 'chmod +x ./install.sh
  * 'install.sh
4. Add Node Server into Polyglot instance.
  * Follow instructions here, starting with "Open Polyglot": https://github.com/Einstein42/udi-polyglotv2/wiki/Creating-a-NodeServer 
5. Select port to use for Rachio websocket traffic to internal Polyglot server (defaults to 3001).  
  * Forward selected port to internal polyglot server.  
  * Add host and port keys to polyglot configuration (See custom configuration parameters below).  Note: Use of a Dynamic DNS service for the external host is recommended.

Any Rachio units associated with the specified API key should now show up in the ISY, hit "Query" if the status fields are empty.  

## Polyglot Custom Configuration Parameters
* REQUIRED: Key:'api_key' Value: See "https://rachio.readme.io/v1.0/docs" for instructions on how to obtain Rachio API Key.
* REQUIRED: Key: 'host' Value: External address for polyglot server (External static IP or Dynamic DNS host name).
* OPTIONAL: Key: 'port' Value: External port (integer) for polyglot server.  Note: This port must be opened through firewall and forwarded to the internal polyglot server.  Defaults to '3001' if no entry given but opening port is not optional (required for Rachio websockets).
* OPTIONAL: Key:'nodeAdditionInterval' Value: On discovery, nodes will be added at this interval (in seconds).
 
## Version History:
* 2.0.0: Rewritten for Polyglot v2.
* 2.1.0: Updated to have each Rachio Device be a primary node
* 2.2.0: Added node addition queue with a default interval of 1 second and removed forced Driver reporting to improve performance in large installs.
* 2.2.1: Corrected "bool" definition in editor profile
* 2.3.0: Simplified driver update logic
* 2.3.1: Corrected bugs relating to setting Rain Delay and Starting Zone
* 2.3.2: Bug fix for zone start log message
* 2.3.3: Bug fixes for schedule durations and season adjustment commands
* 2.4.0: Updated to accommodate changes in Rachio Cloud API.  Added websocket support and caching to minimize API calls.  Removed drivers for "time until next schedule run" because required info was removed from Rachio API.
* 2.4.1: Corrected bug where error is generated if 'port' configuration parameter not defined.  Added closure of server.json file.

## Known Issues:
1. Icons for Rachio Nodes should show up as Irrigation but show up as Bulb.  Appears to be an issue with ISY994i not accepting Irrigation icon type from NLS definition.
2. Commands that allow for a parameter value to be passed don't seem to be present in admin console unless the profile is uploaded twice.  May be an issue with ISY994i (This was developed using version 5.0.10E).