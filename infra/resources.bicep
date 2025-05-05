// -------- infra/resources.bicep --------

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

// --- Container App Config Parameters ---
@description('Specifies the container image to deploy (e.g., myacr.azurecr.io/myapp:latest).')
param containerImage string // Required: Pass this in from workflow (e.g., includes tag/SHA)

@description('Specifies the CPU allocation for the container app.')
param containerAppCpuCoreCount string = (environment == 'prod') ? '1.0' : '0.5' // Kept as string based on previous logs

@description('Specifies the memory allocation for the container app.')
param containerAppMemoryGiB string = (environment == 'prod') ? '2.0Gi' : '1.0Gi'

@description('Minimum replicas for the container app.')
param containerAppMinReplicas int = (environment == 'prod') ? 1 : 0

@description('Maximum replicas for the container app.')
param containerAppMaxReplicas int = (environment == 'prod') ? 5 : 2

// --- Secure Parameters for Secrets ---
@secure()
@description('Required. Cosmos DB connection string.')
param cosmosDbConnectionString string

@secure()
@description('Required. Kinde client secret for backend validation.')
param kindeClientSecret string

@secure()
@description('Required. Stripe secret key (use test key for dev/stg, live key for prod).')
param stripeSecretKey string

@secure()
@description('Required. Connection string for Azure Blob Storage.')
param storageConnectionString string

// --- Variables ---
var uniqueSeed = uniqueString(subscription().subscriptionId)
var shortUniqueSeed = take(uniqueSeed, 8)
var keyVaultName = 'kv-${companyPrefix}-${locationShort}-${environment}-${shortUniqueSeed}'
var storageAccountName = toLower('st${companyPrefix}${locationShort}${take(purpose, 3)}${environment}${shortUniqueSeed}')
var cosmosDbAccountName = 'cosmos-${companyPrefix}-${locationShort}-${purpose}-${environment}'
var containerAppsEnvName = 'cae-${companyPrefix}-${locationShort}-${purpose}-${environment}'
var containerAppName = 'ca-${companyPrefix}-${locationShort}-${purpose}-${environment}'

// Construct ACR name and login server based on parameters
// IMPORTANT: This assumes your manually created ACRs follow this exact naming pattern!
var acrName = toLower('acr${companyPrefix}${purpose}${environment}') // Example: acrsdtaidetectordev
var acrLoginServer = '${acrName}.azurecr.io' // Example: acrsdtaidetectordev.azurecr.io

// Define consistent secret names
var secretNameCosmosConnectionString = 'CosmosDbConnectionString'
var secretNameKindeClientSecret = 'KindeClientSecret'
var secretNameStripeSecretKey = 'StripeSecretKey'
var secretNameStorageConnectionString = 'StorageConnectionString'

// Role Definition IDs
var keyVaultSecretsUserRoleDefinitionId = resourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')

// --- Resource Definitions ---

// Key Vault
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
    enableRbacAuthorization: true
    enablePurgeProtection: true // Keep true per policy
    softDeleteRetentionInDays: (environment == 'prod') ? 90 : 7
  }

  // --- Key Vault Secrets ---
  resource cosmosConnectionStringSecret 'secrets@2023-07-01' = {
    name: secretNameCosmosConnectionString
    properties: {
      value: cosmosDbConnectionString
    }
  }
  resource kindeSecret 'secrets@2023-07-01' = {
    name: secretNameKindeClientSecret
    properties: {
      value: kindeClientSecret
    }
  }
  resource stripeSecret 'secrets@2023-07-01' = {
    name: secretNameStripeSecretKey
    properties: {
      value: stripeSecretKey
    }
  }
  resource storageConnectionStringSecret 'secrets@2023-07-01' = {
    name: secretNameStorageConnectionString
    properties: {
      value: storageConnectionString
    }
  }
}

// Storage Account
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
  properties: {
    // Add specific properties if needed
  }
}

// Container App
resource ca 'Microsoft.App/containerApps@2023-05-01' = {
  name: containerAppName
  location: location
  tags: {
    environment: environment
    application: 'SmartEducator AI Detector'
    purpose: purpose
  }
  identity: {
    type: 'SystemAssigned' // Enable System Assigned Managed Identity
  }
  properties: {
    managedEnvironmentId: cae.id // Link to the Container Apps Environment
    configuration: {
      // Configure registry credentials to use the managed identity
      registries: [
        {
          server: acrLoginServer // Use the variable for ACR FQDN
          identity: 'system'     // Use the system-assigned identity
        }
      ]
      secrets: null // Not using ACA secrets block, using Key Vault instead
      // ingress: { ... } // Add your ingress configuration here if needed
    }
    template: {
      containers: [
        {
          name: 'backend-api' // Container name
          image: containerImage // Image passed from workflow
          resources: {
            cpu: json(containerAppCpuCoreCount) // Use CPU param (as string)
            memory: containerAppMemoryGiB // Use Memory param
          }
          env: [
            // Standard environment variables
            {
              name: 'ENVIRONMENT'
              value: environment
            }
            // App needs to know the Key Vault name to fetch secrets
            {
              name: 'AZURE_KEY_VAULT_NAME'
              value: kv.name
            }
            // Add other non-secret env vars here if needed
          ]
        }
      ]
      scale: {
        minReplicas: containerAppMinReplicas
        maxReplicas: containerAppMaxReplicas
        // rules: [ ... ] // Add scaling rules if needed
      }
    }
  }
  // Add explicit dependsOn for clarity
  dependsOn: [
    cae
    kv
  ]
}

// Key Vault Role Assignment for Container App
resource kvRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  // Scope directly to the Key Vault resource
  scope: kv
  name: guid(kv.id, ca.id, keyVaultSecretsUserRoleDefinitionId) // Create a unique name
  properties: {
    roleDefinitionId: keyVaultSecretsUserRoleDefinitionId
    principalId: ca.identity.principalId // The principal ID of the Container App's Identity
    principalType: 'ServicePrincipal'
  }
  // Ensure Container App identity exists before assigning role
  dependsOn: [
    ca
  ]
}

// ACR Pull Role Assignment for Container App
// Grant Container App's Managed Identity AcrPull role on the ACR

// Construct the ACR Resource ID dynamically based on naming convention
// This assumes the ACR was created manually or by another process following this name pattern

// --- Outputs ---
output keyVaultName string = kv.name
output storageAccountName string = st.name
output cosmosDbAccountName string = cosmos.name
output containerAppsEnvId string = cae.id
output containerAppName string = ca.name
output containerAppPrincipalId string = ca.identity.principalId // Output managed identity ID
