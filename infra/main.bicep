@description('Company prefix for resource names.')
param companyPrefix string = 'sdt'

@description('The purpose of the resources being deployed (e.g., app name).')
param purpose string = 'aidetector'

@description('The deployment environment (e.g., dev, test, prod).')
param environment string = 'dev'

@description('Primary Azure region for resource deployment.')
param location string = 'uksouth' // Keeping full name for deployment location

// --- Variables ---
var locationShort = 'uks' // Short code for naming convention based on location parameter
var rgName = 'rg-${companyPrefix}-${locationShort}-${purpose}-${environment}'
// Generate a unique seed based on the resource group ID for globally unique resource names
var uniqueSeed = uniqueString(resourceGroup().id)
var keyVaultName = 'kv-${companyPrefix}-${locationShort}-${purpose}-${environment}-${uniqueSeed}'
// Storage account names must be 3-24 chars, lowercase alphanumeric only
var storageAccountName = toLower('st${companyPrefix}${locationShort}${purpose}${environment}${uniqueSeed}')
var cosmosDbAccountName = 'cosmos-${companyPrefix}-${locationShort}-${purpose}-${environment}-${uniqueSeed}'
var containerAppsEnvName = 'cae-${companyPrefix}-${locationShort}-${purpose}-${environment}'
var logAnalyticsWorkspaceName = 'log-${companyPrefix}-${locationShort}-${purpose}-${environment}' // Optional LA Workspace

// Define the target scope for the Bicep file
targetScope = 'subscription'

// --- Resources ---

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

// Key Vault for storing secrets
resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  tags: {
    environment: environment
    application: 'SmartEducator AI Detector'
    purpose: purpose
  }
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true // Use RBAC for permissions
  }
  // Deploy within the defined Resource Group
  scope: rg
}

// Storage Account for document uploads
resource st 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  // Name constructed in variables to meet length/char constraints
  name: storageAccountName
  location: location
  tags: {
    environment: environment
    application: 'SmartEducator AI Detector'
    purpose: purpose
  }
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    isHnsEnabled: false
  }
  // Deploy within the defined Resource Group
  scope: rg
}

// Cosmos DB Account with MongoDB API
resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2023-11-15' = {
  // Name constructed in variables
  name: cosmosDbAccountName
  location: location
  kind: 'MongoDB'
  tags: {
    environment: environment
    application: 'SmartEducator AI Detector'
    purpose: purpose
  }
  properties: {
    databaseAccountOfferType: 'Standard'
    locations: [
      {
        locationName: location
        failoverPriority: 0
      }
    ]
    capabilities: [
      {
        name: 'EnableMongo'
      }
      {
        name: 'EnableServerless'
      }
    ]
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
  }
  // Deploy within the defined Resource Group
  scope: rg
}

// Optional: Log Analytics Workspace (needed for CAE custom logging)
// resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
//   name: logAnalyticsWorkspaceName
//   location: location
//   tags: {
//     environment: environment
//     application: 'SmartEducator AI Detector'
//     purpose: purpose
//   }
//   properties: {
//     sku: {
//       name: 'PerGB2018'
//     }
//     retentionInDays: 30
//   }
//   scope: rg
// }

// Container Apps Environment
resource cae 'Microsoft.App/managedEnvironments@2023-05-01' = {
  // Name constructed in variables
  name: containerAppsEnvName
  location: location
  tags: {
    environment: environment
    application: 'SmartEducator AI Detector'
    purpose: purpose
  }
  // Uncomment and configure if using custom Log Analytics
  // properties: {
  //   appLogsConfiguration: {
  //     destination: 'log-analytics'
  //     logAnalyticsConfiguration: {
  //       customerId: logAnalyticsWorkspace.properties.customerId
  //       sharedKey: logAnalyticsWorkspace.listKeys().primarySharedKey
  //     }
  //   }
  // }
  // Deploy within the defined Resource Group
  scope: rg
}

// --- Outputs ---
output resourceGroupName string = rg.name
output keyVaultName string = kv.name
output storageAccountName string = st.name
output cosmosDbAccountName string = cosmos.name
output containerAppsEnvId string = cae.id
// output logAnalyticsWorkspaceId string = logAnalyticsWorkspace.id // Uncomment if LA Workspace is used
