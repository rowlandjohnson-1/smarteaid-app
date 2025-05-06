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
    // Add specific properties if needed, e.g., VNet integration, Log Analytics workspace
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
  properties: { // <<<< THIS BLOCK IS UPDATED BASED ON bicep_container_app_config_v2 >>>>
    managedEnvironmentId: cae.id // Reference to your Container Apps Environment
    configuration: {
      registries: [
        {
          server: acrLoginServer // Your ACR login server (e.g., from a variable)
          identity: 'system'    // Using system-assigned managed identity for ACR pull
        }
      ]
      secrets: [
        // Your existing secrets array for Key Vault integration
        {
          name: secretNameCosmosConnectionString
          keyVaultUrl: '${kv.properties.vaultUri}secrets/${secretNameCosmosConnectionString}'
          identity: 'system'
        }
        {
          name: secretNameKindeClientSecret
          keyVaultUrl: '${kv.properties.vaultUri}secrets/${secretNameKindeClientSecret}'
          identity: 'system'
        }
        {
          name: secretNameStripeSecretKey
          keyVaultUrl: '${kv.properties.vaultUri}secrets/${secretNameStripeSecretKey}'
          identity: 'system'
        }
        {
          name: secretNameStorageConnectionString
          keyVaultUrl: '${kv.properties.vaultUri}secrets/${secretNameStorageConnectionString}'
          identity: 'system'
        }
      ]
      ingress: {
        external: false // Set to true if you need public internet access from outside the VNet/CAE
        targetPort: 8000 // *** Correct: Matches your FastAPI Uvicorn port from logs ***
        transport: 'auto' // Automatically determines HTTP/HTTP2
        // allowInsecure: false // Default is false. Set to true only if terminating SSL at an upstream gateway
                             // and want plain HTTP between the gateway and the container app.
      }
    }
    template: {
      containers: [
        {
          name: 'backend-api' // Your container name
          image: containerImage // *** Correct: Uses the parameter for your actual application image ***
          resources: {
            cpu: json(containerAppCpuCoreCount) // e.g., 0.5
            memory: containerAppMemoryGiB     // e.g., '1.0Gi'
          }
          env: [
            // Your existing environment variables, including those using secretRef
            {
              name: 'ENVIRONMENT'
              value: environment
            }
            {
              name: 'MONGODB_URL'
              secretRef: secretNameCosmosConnectionString
            }
            {
              name: 'KINDE_CLIENT_SECRET'
              secretRef: secretNameKindeClientSecret
            }
            {
              name: 'STRIPE_SECRET_KEY'
              secretRef: secretNameStripeSecretKey
            }
            {
              name: 'AZURE_BLOB_CONNECTION_STRING'
              secretRef: secretNameStorageConnectionString
            }
            {
              name: 'KINDE_DOMAIN'
              value: kindeDomain
            }
            {
              name: 'KINDE_AUDIENCE'
              value: kindeAudience
            }
          ]
          probes: [
            {
              type: 'Liveness' // Determines if the container is running and responsive
              httpGet: {
                path: '/healthz' // *** Correct: Matches your FastAPI liveness endpoint ***
                port: 8000       // *** Correct: Matches your FastAPI Uvicorn port ***
                scheme: 'HTTP'   // Your application serves HTTP on this port
              }
              initialDelaySeconds: 30 // Time (seconds) to wait after container starts before first probe
                                      // Allow time for app init, DB connection (as seen in your logs)
              periodSeconds: 30       // How often (seconds) to perform the probe
              failureThreshold: 3     // Number of consecutive failures after which container is considered unhealthy
              timeoutSeconds: 5       // Seconds after which the probe times out
            }
            {
              type: 'Readiness' // Determines if the container is ready to accept traffic
              httpGet: {
                path: '/readyz'  // *** Correct: Matches your FastAPI readiness endpoint ***
                port: 8000       // *** Correct: Matches your FastAPI Uvicorn port ***
                scheme: 'HTTP'
              }
              initialDelaySeconds: 35 // Give slightly more time for readiness checks (e.g., DB fully ready)
              periodSeconds: 30
              failureThreshold: 3
              timeoutSeconds: 10      // Readiness probe might involve DB checks, so allow a bit more time
            }
            // Optional: Startup Probe (if your app has a very long startup time
            // before even the liveness probe should be active)
            // {
            //   type: 'Startup'
            //   httpGet: {
            //     path: '/healthz' // Can often reuse the liveness path for startup
            //     port: 8000
            //     scheme: 'HTTP'
            //   }
            //   initialDelaySeconds: 10 // Start probing earlier for startup
            //   periodSeconds: 15
            //   failureThreshold: 12    // e.g., 12 attempts * 15s = 3 minutes for startup to complete
            //   timeoutSeconds: 3
            // }
          ]
        }
      ]
      scale: {
        minReplicas: containerAppMinReplicas // e.g., 0 for dev, 1 for prod
        maxReplicas: containerAppMaxReplicas // e.g., 2 for dev, 5 for prod
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
