# Rachio-polyglot
This is the Rachio Node Server for the ISY Polyglot V2 interface.  
(c) fahrer16 aka Brian Feeney.  
MIT license. 

The Rachio water controller uses a cloud-based API that is documented here: https://rachio.readme.io/docs/getting-started.
This node server currently implements the Person, Device, and Zone leaves of the Rachio api.


# Installation Instructions:
1. Backup ISY (just in case)
2. Clone the MagicHome Node Server into the /.polyglot/nodeservers folder for the user that runs polyglot v2:
`Assuming you're logged in as the user that runs polyglot, cd cd ~/.polyglot/nodeservers
`git clone https://github.com/fahrer16/udi-rachio-poly.git
3. Install pre-requisites using install.sh script
  * 'chmod +x ./install.sh
  * 'install.sh
4. Add Node Server into Polyglot instance.
  * Follow instructions here, starting with "Open Polyglot": https://github.com/Einstein42/udi-polyglotv2/wiki/Creating-a-NodeServer 

Any Rachio units associated with the specified API key should now show up in the ISY, hit "Query" if the status fields are empty.  
 
Version History:
2.0.0: Rewritten for Polyglot v2.
 