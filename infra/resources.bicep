@description('Company prefix for resource names.')
param companyPrefix string

@description('The purpose of the resources being deployed (e.g., app name).')
param purpose string

@description('The environment (e.g., dev, test, prod).')
param environment string

@description('Primary Azure region for resource deployment.')
param location string

@description('Short location code for naming convention.')
param locationShort string

// --- Variables ---
// Generate a unique seed based on the subscription ID (since resourceGroup().id isn't available at start)
var uniqueSeed = uniqueString(subscription().subscriptionId)
// Use a shorter unique string (first 8 characters) for storage account
var shortUniqueSeed = take(uniqueSeed, 8)
var keyVaultName = 'kv-${companyPrefix}-${locationShort}-${purpose}-${environment}-${uniqueSeed}'
// Storage account name - shortened to fit 24 character limit
var storageAccountName = toLower('st${companyPrefix}${locationShort}${take(purpose, 3)}${environment}${shortUniqueSeed}')
var cosmosDbAccountName = 'cosmos-${companyPrefix}-${locationShort}-${purpose}-${environment}-${uniqueSeed}'
var containerAppsEnvName = 'cae-${companyPrefix}-${locationShort}-${purpose}-${environment}'
// var logAnalyticsWorkspaceName = 'log-${companyPrefix}-${locationShort}-${purpose}-${environment}' // Commented out to avoid warning

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
    enablePurgeProtection: true // Required by organizational policy
    softDeleteRetentionInDays: 90 // Required with purge protection
  }
}

// Storage Account for document uploads
resource st 'Microsoft.Storage/storageAccounts@2023-01-01' = {
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
}

// Cosmos DB Account with MongoDB API
resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2023-11-15' = {
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
}

// Container Apps Environment
resource cae 'Microsoft.App/managedEnvironments@2023-05-01' = {
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
}

// --- Outputs ---
output keyVaultName string = kv.name
output storageAccountName string = st.name
output cosmosDbAccountName string = cosmos.name
output containerAppsEnvId string = cae.id
