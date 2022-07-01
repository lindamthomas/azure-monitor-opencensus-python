. .\common.ps1

#deploy the arm template
Connect-AzAccount -UseDeviceAuthentication;

SelectSubscription;

$location = "eastus";
$suffix = GetSuffix;
$resourceGroupName = "python-appinsights-$suffix";

$subscriptionId = (Get-AzContext).Subscription.Id
$tenantId = (Get-AzContext).Tenant.Id
$global:logindomain = (Get-AzContext).Tenant.Id;

#create the resource group
New-AzResourceGroup -Name $resourceGroupName -Location $location -force;

#run the deployment...
$templatesFile = "./Artifacts/template.json"
$parametersFile = "./Artifacts/parameters.json"

$content = Get-Content -Path $parametersFile -raw;
$content = $content.Replace("GET-SUFFIX",$suffix);
$content | Set-Content -Path "$($parametersFile).json";

$results = New-AzResourceGroupDeployment -ResourceGroupName $resourceGroupName -TemplateFile $templatesFile -TemplateParameterFile "$($parametersFile).json";

#get the values
$appInsights = Get-AzApplicationInsights -ResourceGroupName $resourceGroupName -Name "python-appinsights-$suffix"

$dataLakeAccountName = "storage$suffix";
$dataLakeStorageUrl = "https://"+ $dataLakeAccountName + ".dfs.core.windows.net/"
$dataLakeStorageBlobUrl = "https://"+ $dataLakeAccountName + ".blob.core.windows.net/"
$dataLakeStorageAccountKey = (Get-AzStorageAccountKey -ResourceGroupName $resourceGroupName -AccountName $dataLakeAccountName)[0].Value
$dataLakeContext = New-AzStorageContext -StorageAccountName $dataLakeAccountName -StorageAccountKey $dataLakeStorageAccountKey

$content = get-content "env.template"
$content = $content.replace("{INSIGHTS_KEY}",$appInsights.InstrumentationKey);
$content = $content.replace("{INSIGHTS_CONNECTION_STRING}",$appInsights.ConnectionString);
$content = $content.replace("{SUFFIX}",$suffix);
$content = $content.replace("{DBUSER}","wsuser");
$content = $content.replace("{DBPASSWORD}","Microsoft123");
$content = $content.replace("{STORAGE_CONNECTION_STRING}",$dataLakeContext.ConnectionString);
#$content = $content.replace("{FUNCTION_URL}","");
set-content ".env" $content;

$content = get-content "./WebApp/.env.example"
$content = $content.replace("{INSIGHTS_KEY}",$appInsights.InstrumentationKey);
$content = $content.replace("{INSIGHTS_CONNECTION_STRING}",$appInsights.ConnectionString);
$content = $content.replace("{SUFFIX}",$suffix);
$content = $content.replace("{DBUSER}","wsuser");
$content = $content.replace("{DBPASSWORD}","Microsoft123");
$content = $content.replace("{STORAGE_CONNECTION_STRING}",$dataLakeContext.ConnectionString);
#$content = $content.replace("{FUNCTION_URL}","");
set-content "./WebApp/.env" $content;