// -------- infra/resources.bicep --------
// Refreshed version for deployment into a new, clean resource group.

@description('Company prefix for resource names.')
param companyPrefix string

@description('The purpose of the resources being deployed (e.g., app name).')
param purpose string

@description('The environment (e.g., dev, test, prod).')
param environment string // This will be 'dev', 'stg', or 'prod'

@description('Primary Azure region for resource deployment.')
param location string

@description('Short location code for naming convention.')
param locationShort string

// --- Container App Config Parameters ---
@description('Specifies the container image to deploy (e.g., myacr.azurecr.io/myapp:latest).')
param containerImage string // Required: Pass this in from workflow (e.g., includes tag/SHA)

@description('Specifies the CPU allocation for the container app.')
param containerAppCpuCoreCount string = (environment == 'prod') ? '1.0' : '0.5'

@description('Specifies the memory allocation for the container app.')
param containerAppMemoryGiB string = (environment == 'prod') ? '2.0Gi' : '1.0Gi'

// MODIFIED: Set minReplicas to 1 for dev to avoid KEDA issues with scale-from-zero without rules.
@description('Minimum replicas for the container app.')
param containerAppMinReplicas int = (environment == 'prod') ? 1 : 1

@description('Maximum replicas for the container app.')
param containerAppMaxReplicas int = (environment == 'prod') ? 5 : 2

// --- Secure Parameters for Secrets ---
@secure()
@description('Required. MongoDB connection string.')
param mongoDbUrl string

@secure()
@description('Required. Kinde client secret for backend validation.')
param kindeClientSecret string

@secure()
@description('Required. Stripe secret key.')
param stripeSecretKey string

@secure()
@description('Required. Connection string for Azure Blob Storage.')
param storageConnectionString string

// --- Kinde non-secret parameters ---
@description('Required. Kinde domain for authentication.')
param kindeDomain string

@description('Required. Kinde audience for authentication.')
param kindeAudience string

// --- Variables ---
var uniqueSeed = uniqueString(resourceGroup().id) // Use resourceGroup().id for seed within RG scope
var shortUniqueSeed = take(uniqueSeed, 8)

var vaultEnvSuffix = (environment == 'stg') ? 'stg' : environment
var storageEnvSuffix = (environment == 'stg') ? 'stg' : environment

var keyVaultName = 'kv-${companyPrefix}-${locationShort}-${vaultEnvSuffix}-${shortUniqueSeed}'
var storageAccountName = toLower('st${companyPrefix}${locationShort}${take(purpose, 3)}${storageEnvSuffix}${shortUniqueSeed}')
var cosmosDbAccountName = 'cosmos-${companyPrefix}-${locationShort}-${purpose}-${environment}'
var containerAppsEnvName = 'cae-${companyPrefix}-${locationShort}-${purpose}-${environment}'
var containerAppName = 'ca-${companyPrefix}-${locationShort}-${purpose}-${environment}'

// Assuming ACR is pre-existing and in the same subscription.
// If ACR is in a different RG, you'll need to adjust the scope for 'acr' resource.
var acrName = toLower('acr${companyPrefix}${purpose}${environment}')
var acrLoginServer = '${acrName}.azurecr.io'

var secretNameCosmosConnectionString = 'cosmos-db-connection-string'
var secretNameKindeClientSecret = 'kinde-client-secret'
var secretNameStripeSecretKey = 'stripe-secret-key'
var secretNameStorageConnectionString = 'storage-connection-string'

var keyVaultSecretsUserRoleDefinitionId = resourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6') // Key Vault Secrets User
var acrPullRoleDefinitionId = resourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d') // AcrPull

// --- Resource Definitions ---

// Reference to an EXISTING Azure Container Registry
// IMPORTANT: Ensure this ACR exists and is in the correct subscription.
// If it's in a different resource group than this deployment, add: scope: resourceGroup('your-acr-resource-group-name')
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: acrName
}

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
    enablePurgeProtection: (environment == 'prod') // Typically true for prod, optional for dev/stg
    softDeleteRetentionInDays: (environment == 'prod') ? 90 : 7
  }

  resource cosmosConnectionStringSecret 'secrets@2023-07-01' = {
    name: secretNameCosmosConnectionString
    properties: { value: mongoDbUrl }
  }
  resource kindeSecret 'secrets@2023-07-01' = {
    name: secretNameKindeClientSecret
    properties: { value: kindeClientSecret }
  }
  resource stripeSecret 'secrets@2023-07-01' = {
    name: secretNameStripeSecretKey
    properties: { value: stripeSecretKey }
  }
  resource storageConnectionStringSecret 'secrets@2023-07-01' = {
    name: secretNameStorageConnectionString
    properties: { value: storageConnectionString }
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
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    isHnsEnabled: false // Set to true if ADLS Gen2 features are needed
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
    locations: [ { locationName: location, failoverPriority: 0 } ]
    capabilities: [ { name: 'EnableMongo' }, { name: 'EnableServerless' } ]
    consistencyPolicy: { defaultConsistencyLevel: 'Session' }
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
    // zoneRedundant: (environment == 'prod') // Consider for production
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
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: cae.id
    configuration: {
      registries: [
        {
          server: acrLoginServer
          identity: 'system' // Use system-assigned identity to pull from ACR
        }
      ]
      secrets: [
        { name: secretNameCosmosConnectionString, keyVaultUrl: '${kv.properties.vaultUri}secrets/${secretNameCosmosConnectionString}', identity: 'system' }
        { name: secretNameKindeClientSecret, keyVaultUrl: '${kv.properties.vaultUri}secrets/${secretNameKindeClientSecret}', identity: 'system' }
        { name: secretNameStripeSecretKey, keyVaultUrl: '${kv.properties.vaultUri}secrets/${secretNameStripeSecretKey}', identity: 'system' }
        { name: secretNameStorageConnectionString, keyVaultUrl: '${kv.properties.vaultUri}secrets/${secretNameStorageConnectionString}', identity: 'system' }
      ]
      ingress: {
        external: false // Set to true for public internet access if needed
        targetPort: 8000 // Port your FastAPI application listens on
        transport: 'auto'
      }
    }
    template: {
      containers: [
        {
          name: 'backend-api' // Your container name
          image: containerImage // Uses the parameter for your application image
          resources: {
            cpu: json(containerAppCpuCoreCount)
            memory: containerAppMemoryGiB
          }
          env: [
            { name: 'ENVIRONMENT', value: environment }
            { name: 'MONGODB_URL', secretRef: secretNameCosmosConnectionString }
            { name: 'KINDE_CLIENT_SECRET', secretRef: secretNameKindeClientSecret }
            { name: 'STRIPE_SECRET_KEY', secretRef: secretNameStripeSecretKey }
            { name: 'AZURE_BLOB_CONNECTION_STRING', secretRef: secretNameStorageConnectionString }
            { name: 'KINDE_DOMAIN', value: kindeDomain }
            { name: 'KINDE_AUDIENCE', value: kindeAudience }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/healthz', port: 8000, scheme: 'HTTP' }
              initialDelaySeconds: 45 // Increased to allow ample startup time
              periodSeconds: 30
              failureThreshold: 3
              timeoutSeconds: 10
            }
            {
              type: 'Readiness'
              httpGet: { path: '/readyz', port: 8000, scheme: 'HTTP' }
              initialDelaySeconds: 60 // Increased to allow ample startup and DB checks
              periodSeconds: 30
              failureThreshold: 3
              timeoutSeconds: 15 // Allow more time for readiness checks
            }
          ]
        }
      ]
      scale: {
        minReplicas: containerAppMinReplicas // Will be 1 for dev
        maxReplicas: containerAppMaxReplicas
      }
    }
  }
  dependsOn: [
    cae
    kv // Ensure Key Vault is available for secret configuration
  ]
}

// Role Assignment: Grant Container App AcrPull role on the ACR
// This assumes 'acr' is an existing resource correctly referenced.
resource acrRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, ca.id, acrPullRoleDefinitionId)
  scope: acr // Scope to the ACR resource
  properties: {
    roleDefinitionId: acrPullRoleDefinitionId
    principalId: ca.identity.principalId
    principalType: 'ServicePrincipal'
  }
  dependsOn: [
    ca // Ensure Container App and its identity exist
    // 'acr' is an existing resource, so direct dependency might not be strictly needed for ordering if ARM can resolve it,
    // but it's good for clarity that this assignment is related to 'ca' and 'acr'.
  ]
}

// Role Assignment: Grant Container App Key Vault Secrets User role on the Key Vault
resource kvRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, ca.id, keyVaultSecretsUserRoleDefinitionId)
  scope: kv // Scope to the Key Vault resource
  properties: {
    roleDefinitionId: keyVaultSecretsUserRoleDefinitionId
    principalId: ca.identity.principalId
    principalType: 'ServicePrincipal'
  }
  dependsOn: [
    ca // Ensure Container App and its identity exist (ca already depends on kv)
  ]
}

// --- Outputs ---
output keyVaultName string = kv.name
output storageAccountName string = st.name
output cosmosDbAccountName string = cosmos.name
output containerAppsEnvId string = cae.id
output containerAppName string = ca.name
output containerAppPrincipalId string = ca.identity.principalId
