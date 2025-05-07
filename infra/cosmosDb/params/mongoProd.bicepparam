using '../mongo.bicep' 

param parLocation =  'uksouth'

param parLockName = 'deleteLock'

// param parLogAnalyticsWorkspaceId = '/subscriptions/fb011ea5-e0b1-4726-b564-8b1d296fb978/resourceGroups/rg-sdt-uks-logging-${parEnv}/providers/Microsoft.OperationalInsights/workspaces/log-sdt-uks-mgmt-${parEnv}'

param parMongoDbAccountName =  'mongo-sdt-uks-aid-${parEnv}'

param parRgName =  'rg-sdt-uks-aid-${parEnv}'

param parEnv =  'prod'

param parSubId =  '50a7d228-9d3a-4067-bb57-aab272dfe934'

// param parDnsSubId =  'a957c3f5-b45c-4848-ba9f-48f1eb1a527d'

param parReplicationLocations = [
  {
    failoverPriority: 0
    isZoneRedundant: false
    locationName: 'uksouth'
  }
]

// param parDnsRgName = 'rg-sdt-uks-dns-prod'

// param parPeRgName = 'rg-sdt-uks-pe-prod'

// param parPeService = 'MongoDB'

param parAllowedIPs = [
  '0.0.0.0/0'
]

// param parIpConfigurations = [
//           {
//             name: 'primary'
//             properties: {
//               privateIPAddress: '10.2.0.28'
//               groupId: parPeService
//               memaidrName: 'mongo-sdt-uks-aid-${parEnv}-uksouth'
//           }
//         }
//         {
//           name: 'secondary'
//           properties: {
//             privateIPAddress: '10.2.0.29'
//             groupId: parPeService
//             memaidrName: 'mongo-sdt-uks-aid-${parEnv}'
//         }
//       }
//     ]

// param parPeName = 'pe-sdt-uks-mongo-${parEnv}'

// param parSubnetId = '/subscriptions/a957c3f5-b45c-4848-ba9f-48f1eb1a527d/resourceGroups/rg-sdt-uks-hub-prod/providers/Microsoft.Network/virtualNetworks/vnet-sdt-uks-hub-prod/subnets/snet-sdt-uks-pe-prod'

param parNetworkAclBypass = 'AzureServices'

param parBackupPolicyContinuousTier = 'Continuous7Days'

param parKvResourceId = '/subscriptions/${parSubId}/resourceGroups/${parRgName}/providers/Microsoft.KeyVault/vaults/kv-sdt-uks-aid-${parEnv}'

param parMongoCsSecretName = 'mongo-aid-cs-${parEnv}'
