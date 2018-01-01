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

Any Rachio units associated with the specified API key should now show up in the ISY, hit "Query" if the status fields are empty.  
 
## Version History:
* 2.0.0: Rewritten for Polyglot v2.
* 2.1.0: Updated to have each Rachio Device be a primary node

## Known Issues:
1. Icons for Rachio Nodes should show up as Irrigation but show up as Bulb.  Appears to be an issue with ISY994i not accepting Irrigation icon type from NLS definition.
2. All node status fields don't seem to be populated initially, possible due to the large number of statuses getting updated simultaneously.  Querying each node separately seems to work fine.
3. Commands that allow for a parameter value to be passed don't seem to be present in admin console unless the profile is uploaded twice.  May be an issue with ISY994i (This was developed using version 5.0.10E).
