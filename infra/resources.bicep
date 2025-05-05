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

// --- Add Container App Config Parameters ---
@description('Specifies the container image to deploy (e.g., myacr.azurecr.io/myapp:latest).')
param containerImage string // Required: Pass this in from workflow (e.g., includes tag/SHA)

@description('Specifies the CPU allocation for the container app.')
param containerAppCpuCoreCount number = (environment == 'prod') ? 1.0 : 0.5

@description('Specifies the memory allocation for the container app.')
param containerAppMemoryGiB string = (environment == 'prod') ? '2.0Gi' : '1.0Gi'

@description('Minimum replicas for the container app.')
param containerAppMinReplicas int = (environment == 'prod') ? 1 : 0

@description('Maximum replicas for the container app.')
param containerAppMaxReplicas int = (environment == 'prod') ? 5 : 2

// --- Add Secure Parameters for Secrets ---
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
var keyVaultName = 'kv-${companyPrefix}-${locationShort}-${environment}-${shortUniqueSeed}' // Adjusted naming slightly
var storageAccountName = toLower('st${companyPrefix}${locationShort}${take(purpose, 3)}${environment}${shortUniqueSeed}')
var cosmosDbAccountName = 'cosmos-${companyPrefix}-${locationShort}-${purpose}-${environment}' // Removed seed - often better without for consistency
var containerAppsEnvName = 'cae-${companyPrefix}-${locationShort}-${purpose}-${environment}'
var containerAppName = 'ca-${companyPrefix}-${locationShort}-${purpose}-${environment}' // Name for the Container App itself

// Define consistent secret names to be used in Key Vault and referenced by the app
var secretNameCosmosConnectionString = 'CosmosDbConnectionString'
var secretNameKindeClientSecret = 'KindeClientSecret'
var secretNameStripeSecretKey = 'StripeSecretKey'
var secretNameStorageConnectionString = 'StorageConnectionString'

// Role Definition ID for Key Vault Secrets User
var keyVaultSecretsUserRoleDefinitionId = resourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')


// --- Resource Definitions ---

// Key Vault
resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  tags: { // Add tags
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
    enableRbacAuthorization: true // RBAC is required for Managed Identity access
    // Purge protection might prevent immediate deletion/recreation in dev, consider making it conditional
    enablePurgeProtection: (environment == 'prod') ? true : false
    softDeleteRetentionInDays: (environment == 'prod') ? 90 : 7
  }

  // --- Add Secrets Directly to Key Vault ---
  // Note: Bicep needs Microsoft.KeyVault/vaults/accessPolicies or RBAC assignments for itself to set secrets
  // RBAC is preferred. Ensure the identity running the Bicep deployment has Key Vault Secrets Officer role on the KV or Subscription.
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
  tags: { // Add tags
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
  tags: { // Add tags
    environment: environment
    application: 'SmartEducator AI Detector'
    purpose: purpose
  }
  properties: {
    // Consider making offer type conditional if cost is a concern for dev/stg
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
      { // Use Serverless only if appropriate, otherwise remove this capability
        name: 'EnableServerless'
      }
    ]
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    // Enable RBAC for Cosmos data plane access if needed later
    // disableLocalAuth: false
  }
}

// Container Apps Environment
resource cae 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: containerAppsEnvName
  location: location
  tags: { // Add tags
    environment: environment
    application: 'SmartEducator AI Detector'
    purpose: purpose
  }
  properties: {
    // Assign Key Vault for ACA environment secrets if needed (optional but good practice)
    // daprAIInstrumentationKey: applicationInsights.properties.instrumentationKey // If using App Insights
    // zoneRedundant: (environment == 'prod') ? true : false // Example: Zonal redundancy for prod
  }
}

// --- ADD THE CONTAINER APP DEFINITION ---
resource ca 'Microsoft.App/containerApps@2023-05-01' = {
  name: containerAppName
  location: location
  tags: { // Add tags
    environment: environment
    application: 'SmartEducator AI Detector'
    purpose: purpose
  }
  // Enable System Assigned Managed Identity
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: cae.id // Link to the Container Apps Environment
    configuration: {
      // Use Key Vault for secrets instead of ACA secrets block
      secrets: null
      // ingress: { // Define ingress if the app needs to be publicly accessible
      //   external: true
      //   targetPort: 80 // Or whatever port your FastAPI app listens on (e.g., 8000)
      //   transport: 'auto'
      // }
      // activeRevisionsMode: 'single' // Or 'multiple' for staged rollouts
    }
    template: {
      containers: [
        {
          name: 'backend-api' // Choose a container name
          image: containerImage // Use the parameter for the image
          resources: {
            cpu: json(string(containerAppCpuCoreCount))
            memory: containerAppMemoryGiB
          }
          env: [
            // Standard environment variables
            {
              name: 'ENVIRONMENT'
              value: environment
            }
            // --- Environment variables referencing Key Vault secrets ---
            // The app needs to know the Key Vault name to construct the reference URI,
            // or use specific ACA Key Vault reference syntax if available/preferred.
            // Simpler approach: Pass Key Vault Name as an Env Var
            {
              name: 'AZURE_KEY_VAULT_NAME'
              value: kv.name
            }
            // App code will use this name + the secret name + Managed Identity to fetch secrets.
            // Alternatively, use the ACA specific syntax:
            // {
            //   name: 'DATABASE_URL'
            //   secretRef: secretNameCosmosConnectionString // MUST match name in Key Vault!
            // },
            // {
            //   name: 'KINDE_CLIENT_SECRET'
            //   secretRef: secretNameKindeClientSecret
            // }, // ... and so on for Stripe, Storage
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
}

// --- Grant Container App's Managed Identity access to Key Vault ---
resource kvRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, ca.id, keyVaultSecretsUserRoleDefinitionId) // Create a unique name for the role assignment
  scope: kv // Scope the assignment to the Key Vault
  properties: {
    roleDefinitionId: keyVaultSecretsUserRoleDefinitionId
    principalId: ca.identity.principalId // The principal ID of the Container App's System Assigned Identity
    principalType: 'ServicePrincipal'
  }
}


// --- Outputs ---
output keyVaultName string = kv.name
output storageAccountName string = st.name
output cosmosDbAccountName string = cosmos.name
output containerAppsEnvId string = cae.id
output containerAppName string = ca.name // Output the Container App name
output containerAppPrincipalId string = ca.identity.principalId // Output the managed identity ID (useful for debugging)
