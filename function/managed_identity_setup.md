# Azure Managed Identity Setup Guide

## Changes Made to Code

### 1. **Removed Connection Strings**
- No more `STORAGE_CONNECTION_STRING` or `EventHubConnectionString`
- Using `DefaultAzureCredential()` for authentication

### 2. **New Environment Variables**
```
STORAGE_ACCOUNT_NAME=yourstorageaccountname
EVENTHUB_NAMESPACE=your-eventhub-namespace  
EVENTHUB_NAME=your-eventhub-name
EventHubConnection__fullyQualifiedNamespace=your-eventhub-namespace.servicebus.windows.net
```

### 3. **Updated Dependencies**
- Added `azure-identity` package for managed identity support

## Azure Configuration Steps

### Step 1: Enable System-Assigned Managed Identity

**Via Azure Portal:**
1. Go to your Function App in Azure Portal
2. Navigate to **Identity** → **System assigned**
3. Set Status to **On**
4. Click **Save**
5. Note the **Object (principal) ID** - you'll need this

**Via Azure CLI:**
```bash
az functionapp identity assign --name <function-app-name> --resource-group <resource-group>
```

### Step 2: Grant Event Hub Permissions

**Via Azure Portal:**
1. Go to your **Event Hub Namespace**
2. Navigate to **Access control (IAM)**
3. Click **Add** → **Add role assignment**
4. Select role: **Azure Event Hubs Data Receiver**
5. Assign access to: **Managed Identity**
6. Select your Function App's managed identity
7. Click **Save**

**Via Azure CLI:**
```bash
# Get the Function App's principal ID
PRINCIPAL_ID=$(az functionapp identity show --name <function-app-name> --resource-group <resource-group> --query principalId -o tsv)

# Assign Event Hub Data Receiver role
az role assignment create \
  --assignee $PRINCIPAL_ID \
  --role "Azure Event Hubs Data Receiver" \
  --scope "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.EventHub/namespaces/<eventhub-namespace>"
```

### Step 3: Grant Storage Account Permissions

**Via Azure Portal:**
1. Go to your **Storage Account**
2. Navigate to **Access control (IAM)**
3. Click **Add** → **Add role assignment**
4. Select role: **Storage Blob Data Contributor**
5. Assign access to: **Managed Identity**
6. Select your Function App's managed identity
7. Click **Save**

**Via Azure CLI:**
```bash
# Assign Storage Blob Data Contributor role
az role assignment create \
  --assignee $PRINCIPAL_ID \
  --role "Storage Blob Data Contributor" \
  --scope "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.Storage/storageAccounts/<storage-account-name>"
```

## Application Settings Configuration

### In Azure Portal:
1. Go to Function App → **Configuration** → **Application settings**
2. Add these settings:

```
EventHubConnection__fullyQualifiedNamespace = your-eventhub-namespace.servicebus.windows.net
STORAGE_ACCOUNT_NAME = yourstorageaccountname  
EVENTHUB_NAMESPACE = your-eventhub-namespace
EVENTHUB_NAME = your-eventhub-name
FLUSH_INTERVAL_SECONDS = 300
MAX_LINES_PER_FLUSH = 1000
```

### Via Azure CLI:
```bash
az functionapp config appsettings set \
  --name <function-app-name> \
  --resource-group <resource-group> \
  --settings \
    "EventHubConnection__fullyQualifiedNamespace=your-eventhub-namespace.servicebus.windows.net" \
    "STORAGE_ACCOUNT_NAME=yourstorageaccountname" \
    "EVENTHUB_NAMESPACE=your-eventhub-namespace" \
    "EVENTHUB_NAME=your-eventhub-name" \
    "FLUSH_INTERVAL_SECONDS=300" \
    "MAX_LINES_PER_FLUSH=1000"
```

## Benefits of Managed Identity

1. **No Secrets Management**: No connection strings or keys to rotate
2. **Enhanced Security**: Credentials managed by Azure AD
3. **Automatic Rotation**: Azure handles credential lifecycle
4. **Principle of Least Privilege**: Grant only required permissions
5. **Audit Trail**: All access is logged in Azure AD

## Local Development

For local development, you have several options:

### Option 1: Azure CLI Authentication
```bash
az login
# Your local DefaultAzureCredential will use your Azure CLI login
```

### Option 2: Visual Studio Code Authentication
- Install Azure Account extension
- Sign in to Azure through VS Code

### Option 3: Service Principal (for CI/CD)
Set these environment variables:
```
AZURE_CLIENT_ID=<service-principal-client-id>
AZURE_CLIENT_SECRET=<service-principal-secret>  
AZURE_TENANT_ID=<tenant-id>
```

## Troubleshooting

### Common Issues:

1. **"Access Denied" errors**: Check role assignments are correct
2. **"Audience validation failed"**: Verify namespace URLs are correct
3. **Local development issues**: Ensure you're logged into Azure CLI or VS Code

### Useful Commands:
```bash
# Check current Azure CLI login
az account show

# List role assignments for the managed identity
az role assignment list --assignee <principal-id>

# Test blob storage access
az storage blob list --account-name <storage-account> --container-name <container> --auth-mode login
```