// -------- infra/resources.bicep --------

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

@description('Minimum replicas for the container app.')
param containerAppMinReplicas int = (environment == 'prod') ? 1 : 0

@description('Maximum replicas for the container app.')
param containerAppMaxReplicas int = (environment == 'prod') ? 5 : 2

// --- Secure Parameters for Secrets ---
// These are STILL required by this module to CREATE the secrets in Key Vault
@secure()
@description('Required. MongoDB connection string (formerly Cosmos DB).')
param mongoDbUrl string

@secure()
@description('Required. Kinde client secret for backend validation.')
param kindeClientSecret string

@secure()
@description('Required. Stripe secret key (use test key for dev/stg, live key for prod).')
param stripeSecretKey string

@secure()
@description('Required. Connection string for Azure Blob Storage.')
param storageConnectionString string

// --- Add Kinde non-secret parameters ---
@description('Required. Kinde domain for authentication.')
param kindeDomain string

@description('Required. Kinde audience for authentication.')
param kindeAudience string
// --- End Kinde non-secret parameters ---

// --- Variables ---
var uniqueSeed = uniqueString(subscription().subscriptionId)
var shortUniqueSeed = take(uniqueSeed, 8)

// --- Naming Convention Fixes for 'stg' ---
var vaultEnvSuffix = (environment == 'stg') ? 'stg' : environment // Use 'stg' if environment is 'stg'
var storageEnvSuffix = (environment == 'stg') ? 'stg' : environment // Use 'stg' if environment is 'stg'
// --- End Naming Fixes ---

var keyVaultName = 'kv-${companyPrefix}-${locationShort}-${vaultEnvSuffix}-${shortUniqueSeed}' // Use suffix
var storageAccountName = toLower('st${companyPrefix}${locationShort}${take(purpose, 3)}${storageEnvSuffix}${shortUniqueSeed}') // Use suffix
var cosmosDbAccountName = 'cosmos-${companyPrefix}-${locationShort}-${purpose}-${environment}' // Stays same
var containerAppsEnvName = 'cae-${companyPrefix}-${locationShort}-${purpose}-${environment}' // Stays same
var containerAppName = 'ca-${companyPrefix}-${locationShort}-${purpose}-${environment}' // Stays same

// Construct ACR name and login server based on parameters
var acrName = toLower('acr${companyPrefix}${purpose}${environment}') // Uses 'stg' correctly now
var acrLoginServer = '${acrName}.azurecr.io' // Example: acrsdtaidetectorstg.azurecr.io

// Define consistent secret names (used for creation in KV and referencing in ACA)
var secretNameCosmosConnectionString = 'cosmos-db-connection-string' // All lowercase, hyphens
var secretNameKindeClientSecret = 'kinde-client-secret'
var secretNameStripeSecretKey = 'stripe-secret-key'
var secretNameStorageConnectionString = 'storage-connection-string'

// Role Definition IDs
var keyVaultSecretsUserRoleDefinitionId = resourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6') // Key Vault Secrets User Role ID
var acrPullRoleDefinitionId = resourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d') // AcrPull Role ID

// --- Resource Definitions ---

// Add this to reference the ACR resource
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: acrName // Use the variable defining your ACR name
}

// Key Vault
resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName // Uses corrected name logic
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
    enableRbacAuthorization: true // RBAC must be enabled for Managed Identity access
    enablePurgeProtection: true // Keep true per policy
    softDeleteRetentionInDays: (environment == 'prod') ? 90 : 7
  }

  // --- Key Vault Secrets (Creation using parameters) ---
  resource cosmosConnectionStringSecret 'secrets@2023-07-01' = {
    name: secretNameCosmosConnectionString // Use variable for name
    properties: {
      value: mongoDbUrl
    }
  }
  resource kindeSecret 'secrets@2023-07-01' = {
    name: secretNameKindeClientSecret // Use variable for name
    properties: {
      value: kindeClientSecret
    }
  }
  resource stripeSecret 'secrets@2023-07-01' = {
    name: secretNameStripeSecretKey // Use variable for name
    properties: {
      value: stripeSecretKey
    }
  }
  resource storageConnectionStringSecret 'secrets@2023-07-01' = {
    name: secretNameStorageConnectionString // Use variable for name
    properties: {
      value: storageConnectionString
    }
  }
}

// Storage Account
resource st 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageAccountName // Uses corrected name logic
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
          identity: 'system'    // Use the system-assigned identity
        }
      ]

      // --- REFINED CORRECTED SECRETS BLOCK ---
      secrets: [
        // For each secret you need from Key Vault, define it here.
        // The 'name' is the internal ACA name used by secretRef.
        // ACA implicitly uses this 'name' to look up the secret with the same name in Key Vault
        // using the specified identity and keyVaultUrl.
        {
          name: secretNameCosmosConnectionString // Internal ACA Name (e.g., 'CosmosDbConnectionString')
          keyVaultUrl: kv.properties.vaultUri   // Base Vault URL
          identity: 'system'                    // Use system identity to access KV
        }
        {
          name: secretNameKindeClientSecret     // Internal ACA Name ('KindeClientSecret')
          keyVaultUrl: kv.properties.vaultUri
          identity: 'system'
        }
        {
          name: secretNameStripeSecretKey       // Internal ACA Name ('StripeSecretKey')
          keyVaultUrl: kv.properties.vaultUri
          identity: 'system'
        }
        {
          name: secretNameStorageConnectionString // Internal ACA Name ('StorageConnectionString')
          keyVaultUrl: kv.properties.vaultUri
          identity: 'system'
        }
      ]
      // ingress: { ... } // Add your ingress configuration here if needed
    }
    template: {
      containers: [
        {
          name: 'backend-api' // Container name
          image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
          resources: {
            cpu: json(containerAppCpuCoreCount)
            memory: containerAppMemoryGiB
          }
          env: [
            {
              name: 'ENVIRONMENT'
              value: environment
            }
            // --- Secrets Referenced from Key Vault ---
            {
              name: 'MONGODB_URL'
              secretRef: secretNameCosmosConnectionString // References the secret NAME in Key Vault
            }
            {
              name: 'KINDE_CLIENT_SECRET'
              secretRef: secretNameKindeClientSecret // References the secret NAME in Key Vault
            }
            {
              name: 'STRIPE_SECRET_KEY'
              secretRef: secretNameStripeSecretKey // References the secret NAME in Key Vault
            }
            {
              name: 'AZURE_BLOB_CONNECTION_STRING'
              secretRef: secretNameStorageConnectionString // References the secret NAME in Key Vault
            }
            // --- Non-Secrets remain using 'value' ---
            {
              name: 'KINDE_DOMAIN'
              value: kindeDomain // Keep as direct value
            }
            {
              name: 'KINDE_AUDIENCE'
              value: kindeAudience // Keep as direct value
            }
            // Optional: Add KINDE_CLIENT_ID if needed (would require adding param and passing value)
            // {
            //   name: 'KINDE_CLIENT_ID'
            //   value: kindeClientId // Assuming you add a kindeClientId param
            // }
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
  // MODIFIED: Add explicit dependency on Key Vault
  dependsOn: [
    cae
    kv // Explicitly depend on Key Vault as we reference its properties
  ]
}

// Role Assignment: Grant Container App AcrPull role on the ACR
resource acrRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, ca.id, acrPullRoleDefinitionId) // Unique name for the role assignment
  scope: acr // IMPORTANT: Scope the assignment directly to the ACR resource
  properties: {
    roleDefinitionId: acrPullRoleDefinitionId
    principalId: ca.identity.principalId // The Container App's Managed Identity principal ID
    principalType: 'ServicePrincipal'
  }
  dependsOn: [
    ca // Ensure Container App and its identity exist
    acr // Ensure ACR reference is resolved
  ]
}

// NEW: Key Vault Role Assignment for Container App (Uncommented and verified)
resource kvRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: kv // Scope directly to the Key Vault resource
  name: guid(kv.id, ca.id, keyVaultSecretsUserRoleDefinitionId) // Create a unique name
  properties: {
    roleDefinitionId: keyVaultSecretsUserRoleDefinitionId // Use variable for Key Vault Secrets User role
    principalId: ca.identity.principalId // The principal ID of the Container App's Identity
    principalType: 'ServicePrincipal'
  }
  // Ensure Container App identity exists before assigning role
  dependsOn: [
    ca // Depends on Container App (which depends on KV)
  ]
}

// --- Outputs ---
output keyVaultName string = kv.name
output storageAccountName string = st.name
output cosmosDbAccountName string = cosmos.name
output containerAppsEnvId string = cae.id
output containerAppName string = ca.name
output containerAppPrincipalId string = ca.identity.principalId // Output managed identity ID