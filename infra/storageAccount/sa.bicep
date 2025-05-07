targetScope = 'subscription'

param parRgName string

param parSubId string

param parEnv string

param parSaName string 

param parSaKind string

param parLocation string 

param parSkuName string

param parKvName string

param parKvSecretName string

module storageAccount 'br/public:avm/res/storage/storage-account:0.19.0' = {
  scope: resourceGroup(parSubId, parRgName)
  name: 'storageAccountDeployment-${parEnv}'
  params: {
    // Required parameters
    name: parSaName
    // Non-required parameters
    kind: parSaKind
    location: parLocation
    skuName: parSkuName
  }
}

resource storageAccountExisting 'Microsoft.Storage/storageAccounts@2023-01-01' existing = {
  name: parSaName
  scope: resourceGroup(parSubId, parRgName)
}

var varSaCs = 'DefaultEndpointsProtocol=https;AccountName=${parSaName};AccountKey=${storageAccountExisting.listKeys().keys[0].value};EndpointSuffix=${environment().suffixes.storage}'

module keyVaultSecretModule '../modules/KeyVaultSecret.bicep' = {
  scope: resourceGroup(parSubId, parRgName)
  name: 'setKeyVaultSecret'
  params: {
    parKvName: parKvName
    parSecretName: parKvSecretName
    parSecretValue: varSaCs
  }
}
