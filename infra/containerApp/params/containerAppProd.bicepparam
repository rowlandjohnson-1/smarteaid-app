using '../containerApp.bicep'

param parUserMi = '/subscriptions/dbdaefc1-1c79-417b-a7b9-4ac0a2559ee7/resourcegroups/rg-sdt-uks-identity-prod/providers/Microsoft.ManagedIdentity/userAssignedIdentities/mi-sdt-uks-kv-prod'

param parEnvVariables01 = [
  {
    name: 'var1'
    value: 'value1'
  }
  // {
  //   // name: 'ContainerAppKeyVaultStoredSecretName'
  //   // secretRef: 'keyvaultstoredsecret'
  // }
]

// Follow the secret refs from the env variables and registries
param parSecretList = [
        {
          name: 'containerappstoredsecret'
          value: 'test'
        }
        {
          identity: parUserMi
          keyVaultUrl: 'https://kv-sdt-uks-idty-prod.vault.azure.net/secrets/acrsdtuksbeprod-password/5c9f7321ecc948f7b3aff53c5ddf06d4'
          name: 'acrsdtuksbeprod-password'
        }
      ]

param parProbes01 = [
          // {
          //   httpGet: {
          //     httpHeaders: []
          //     path: '/'
          //     port: 2003
          //   }
          //   initialDelaySeconds: 3
          //   periodSeconds: 3
          //   type: 'Liveness'
          // }
        ]

param parContainerName01 = 'container-sdt-uks-ingest-prod'

param parContainerResources01 = {
          cpu: '1.0'
          memory: '2Gi'
          ephemeralStorage: '1Gi'
        }

param parScaleRules = [
    ]

param parScaleMaxReplicas = 20

param parScaleMinReplicas = 2

param parRegistriesCredentials = [
  {
    server: 'acrsdtuksbeprod.azurecr.io'
    username: 'acrsdtuksbeprod'
    passwordSecretRef: 'acrsdtuksbeprod-password'
  }
]

param parContainerAppName = 'ca-sdt-uks-ingest-prod'

// Set to false to entirely disable ingress and void the other ingress settings
param parDisableIngress = false

param parContainerImage01 = 'acrsdtuksbeprod.azurecr.io/sendient/unoserver:latest'

param parTargetPort = 2003

// For CI/CD, use output of container env deployment
param parContainerEnvResourceId = '/subscriptions/13c990e9-03e7-4a84-b137-5095c6a0246e/resourceGroups/rg-sdt-uks-workloads-prod/providers/Microsoft.App/managedEnvironments/ce-sdt-uks-ingest-prod'

param parRgName = 'rg-sdt-uks-workloads-prod'

param parSubId = '13c990e9-03e7-4a84-b137-5095c6a0246e'

param parAlowHttp = true

param parLocation = 'uksouth'

param parMiEnabled = true

param parActiveRevisionsMode = 'Single'

param parDapr = {
  
}

param parRoleAssignments = [
      {
        principalId: '90082145-1296-4cfd-8b33-066abe5f9dd6'
        principalType: 'ServicePrincipal'
        roleDefinitionIdOrName: 'Contributor'
      }
      {
        principalId: '1af95bfa-a983-4aaf-b606-67295186ce62'
        principalType: 'ServicePrincipal'
        roleDefinitionIdOrName: 'Contributor'
      }
    ]

param parIPRules = []
