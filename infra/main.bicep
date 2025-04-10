@description('Company prefix for resource names.')
param companyPrefix string = 'sdt'

@description('The purpose of the resources being deployed (e.g., app name).')
param purpose string = 'aidetector'

@description('The environment (e.g., dev, test, prod).')
param environment string = 'dev'

@description('Primary Azure region for resource deployment.')
param location string = 'uksouth'

// Define the target scope for the Bicep file
targetScope = 'subscription'

// --- Variables ---
var locationShort = 'uks' // Short code for naming convention
var rgName = 'rg-${companyPrefix}-${locationShort}-${purpose}-${environment}'

// Resource Group
resource rg 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: rgName
  location: location
  tags: {
    environment: environment
    application: 'SmartEducator AI Detector'
    purpose: purpose
  }
}

// Deploy all resources within the resource group using a module
module resources 'resources.bicep' = {
  name: 'resourcesDeployment'
  scope: rg
  params: {
    companyPrefix: companyPrefix
    purpose: purpose
    environment: environment
    location: location
    locationShort: locationShort
  }
}

// --- Outputs ---
output resourceGroupName string = rg.name
output keyVaultName string = resources.outputs.keyVaultName
output storageAccountName string = resources.outputs.storageAccountName
output cosmosDbAccountName string = resources.outputs.cosmosDbAccountName
output containerAppsEnvId string = resources.outputs.containerAppsEnvId
