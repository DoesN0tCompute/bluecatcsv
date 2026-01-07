# Table of Contents

- [Address Manager RESTful v2 API Guide](#address-manager-restful-v2-api-guide)
  - [Table of Contents](#table-of-contents)
  - [Introduction](#introduction)
  - [Creating an API session](#creating-an-api-session)
    - [Authentication](#authentication)
    - [Using the Swagger UI](#using-the-swagger-ui)
    - [Using an API client](#using-an-api-client)
    - [. Using a web browser](#using-a-web-browser)
  - [RESTful v2 API Format](#restful-v2-api-format)
    - [. HTTP request methods](#http-request-methods)
    - [. HTTP response status codes](#http-response-status-codes)
    - [. HTTP headers](#http-headers)
    - [. Supported media types](#supported-media-types)
  - [Resource representation](#resource-representation)
    - [. Resources](#resources)
    - [Collections](#collections)
    - [. Errors](#errors)
    - [. HAL links](#hal-links)
  - [Query parameters](#query-parameters)
    - [. Referencing fields](#referencing-fields)
    - [. Filter](#filter)
    - [. Fields](#fields)
    - [. Ordering](#ordering)
    - [. Pagination](#pagination)
  - [RESTful v2 API examples](#restful-v2-api-examples)
    - [. Basic operations](#basic-operations)
  - [v1 REST API to RESTful v2 API migration guide](#v1-rest-api-to-restful-v2-api-migration-guide)
    - [A-F API endpoints](#a-f-api-endpoints)
    - [G-L API endpoints](#g-l-api-endpoints)
    - [M-R API endpoints](#m-r-api-endpoints)
    - [S-Z API endpoints](#s-z-api-endpoints)
  - [Terms and Conditions](#terms-and-conditions)
    - [Copyright](#copyright)
    - [Trademarks](#trademarks)

# Address Manager RESTful v2 API Guide

## Table of Contents

1. [Introduction](#1-introduction)
2. [Creating an API session](#2-creating-an-api-session)
 * 2.1. Authentication 
 + 2.1.1. Basic authentication
 + 2.1.2. Bearer authentication
 * 2.2. Using the Swagger UI 
 * 2.3 Using an API client 
 * 2.4. Using a web browser 
3. [RESTful v2 API Format](#3-restful-v2-api-format)
 * 3.1. HTTP request methods 
 * 3.2. HTTP response status codes 
 * 3.3. HTTP headers
 * 3.4. Supported media types 
4. [Resource representation](#4-resource-representation)
 * 4.1. Resources 
 * 4.2 Collections 
 * 4.3. Errors 
 * 4.4. HAL links 
5. [Query parameters](#5-query-parameters)
 * 5.1. Referencing fields 
 * 5.2. Filter 
 * 5.3. Fields 
 + 5.3.1. Embedding subcollections
 * 5.4. Ordering 
 * 5.5. Pagination 
6. [RESTful v2 API examples](#6-restful-v2-api-examples)
 * 6.1. Basic operations 
 + 6.1.1. Creating resources
 + 6.1.2. Retrieving resources
 + 6.1.3. Updating resources
 + 6.1.4. Deleting resources
7. [v1 REST API to RESTful v2 API migration guide](#7-v1-rest-api-to-restful-v2-api-migration-guide)
8. [Terms and Conditions](#8-terms-and-conditions)

## Introduction

Welcome to the BlueCat Address Manager RESTful v2 API Guide.

**Attention:** This guide exclusively covers the new Address Manager RESTful v2 API. For information about the Address Manager Legacy v1 API, refer to the Address Manager Legacy v1 API Guide.

This guide is meant to be a companion to the Swagger documentation accessible on Address Manager v9.5 servers at http://{Address_Manager_IP}/api/docs. All v2 RESTful API endpoints and resources are documented in the interactive Swagger UI. Users can also download the RESTful v2 API OpenAPI (OAS3) document and import it into their API client of choice. For more information, refer to Creating an API session.

The RESTful v2 API adheres to REST architectural constraints and the HTTP 1.1 standard. Address Manager objects are presented as resources. Each resource has a unique endpoint, and related resources are grouped in collections. For more information, refer to Resource representation.

The RESTful v2 API is hypermedia driven. When using the API, you can use links to navigate to related resources or child resources of the requested resource. For more information, refer to HAL links.

The RESTful v2 API allows users to structure response data with a variety of query parameters. For more information, refer to Query parameters.

The RESTful v2 API currently covers most v1 REST API functionality, and is intended to replace the v1 REST API in the future. For a mapping of v1 REST APIs to RESTful v2 API endpoints, and a reference for currently unsupported actions, refer to the v1 REST API to RESTful v2 API migration guide.

## Creating an API session

There are multiple ways to create a session and interact with the new Address Manager 9.5 RESTful v2 API. Users can view endpoints and perform operations with the built-in Swagger UI, interact with an external API client, or browse endpoints directly with a web browser. For authentication, the RESTful v2 API supports the Basic and Bearer HTTP authentication schemes.

### Authentication

#### Basic authentication

**Authorization header**

To authenticate using Basic authentication, the Authorization header must specify the Basic scheme followed by the base64 encoding of the requester's username and API token delimited by a colon. The API token is returned by the /api/v2/sessions endpoint as apiToken. For convenience, the /api/v2/sessions endpoint also returns a basicAuthenticationCredentials field containing the encoded username and token, which can be injected directly into the Authorization header.

**Example header:**
```
Authorization: Basic {basicAuthenticationCredentials}
```

**Creating a session via the /api/v2/sessions endpoint**

Create an API session by sending a POST request to the /api/v2/sessions endpoint with a request body containing the user's credentials.

**Request**
```http
POST http://{Address_Manager_IP}/api/v2/sessions
Content-Type: application/json

{
 "username": "user1",
 "password": "pass1"
}
```

**Sample curl call**
```bash
curl -v -d '{"username":"user1", "password":"pass1"}' -X POST -H "Content-Type: application/json" http://{Address_Manager_IP}/api/v2/sessions
```

The response will contain an apiToken value that can be combined with the username and encoded for the Authorization header of RESTful v2 API requests. The response will also contain a basicAuthenticationCredentials field that can be injected directly.

**Response**
```http
HTTP/1.1 201 Created
Content-Type: application/hal+json

{
 "id": 62,
 "type": "UserSession",
 "apiToken": "/LOcpzfqKXgvt3PH0xYNhFqTewfnF5SNz7Fh/ST8",
 "apiTokenExpirationDateTime": "2023-01-21T21:40:48Z",
 "basicAuthenticationCredentials": "YXBpOi9MT2NwemZxS1hndnQzUEgweFlOaEZxVGV3Zm5GNVNOejdGaC9TVDg=",
 "state": "LOGGED_IN",
 "remoteAddress": "192.168.217.248",
 "readOnly": false,
 "loginDateTime": "2023-01-20T21:40:48Z",
 "logoutDateTime": null,
 "response": null,
 "user": {
 "id": 100893,
 "type": "User",
 "name": "user1",
 "_links": {
 "self": {
 "href": "/api/v2/users/100893"
 }
 }
 },
 "authenticator": {
 "id": 2,
 "type": "AddressManagerAuthenticator",
 "name": "proteusAuthenticator",
 "_links": {
 "self": {
 "href": "/api/v2/authenticators/2"
 }
 }
 },
 "_links": {
 "self": {
 "href": "/api/v2/sessions/62"
 },
 "collection": {
 "href": "/api/v2/sessions"
 }
 }
}
```

#### Bearer authentication

**Authorization header**

The Address Manager RESTful v2 API supports OAuth 2.0 authentication through Bearer Tokens. To authenticate using Bearer authentication, the Authorization header must specify the Bearer scheme followed by the access token provided by the authorization server.

**Example header:**
```
Authorization: Bearer {Token}
```

**Configuring OAuth 2.0 via the Address Manager UI**

OAuth 2.0 can be configured for the RESTful v2 API through the Address Manager user interface, in the same way it is configured for the v1 REST API. Refer to OAuth API authorization in the Address Manager Administration Guide for more information.

**Configuring OAuth 2.0 via the /api/v2/authenticators endpoint**

OAuth 2.0 can be configured directly through the RESTful v2 API with the /api/v2/authenticators endpoint. Refer to the RESTful v2 API OpenAPI (OAS3) document or Swagger UI for more information.

### Using the Swagger UI

The Address Manager RESTful v2 API includes a built-in interactive Swagger UI with full documentation and API functionality.

Access the Swagger UI by entering the following URL in a supported web browser:
```
http://{Address_Manager_IP}/api/docs
```

**Authentication for the Swagger UI**

Authenticate the Swagger UI session by selecting the Authorize button at the top of the Swagger UI and entering Basic (User name and apiToken) or Bearer (Bearer Token) credentials to authenticate the API session.

### Using an API client

The Address Manager RESTful v2 API is fully documented in OpenAPI (OAS3) format, which can be imported or converted for use with compatible API clients.

**RESTful v2 API OpenAPI (OAS3) document**

Access the RESTful v2 API OAS3 document at the following URL:
```
http://{Address_Manager_IP}/api/openapi.json
```

**Using the RESTful v2 API with Postman**

Postman is an API platform for building and using APIs. The RESTful v2 API OAS3 document can be imported directly into Postman by downloading and importing the OAS3 document, or providing the URL for the document location.

### . Using a web browser

Users can browse Address Manager RESTful v2 API endpoints directly in a supported web browser using endpoint URLs. Browser navigation is supported for Google Chrome, Mozilla Firefox, and Microsoft Edge browsers.

Enter the following URL in the location bar to access the root collection:
```
http://{Address_Manager_IP}/api/v2/
```

The browser will prompt for Basic authentication credentials. Enter the User name and apiToken generated when creating an API session, as detailed in Basic authentication.

**Tip:** If the prompt is closed before entering authentication details, subsequent attempts to reach the endpoint will return a 401 Unauthorized error. Clear the browser cookies to bring up the authentication prompt again on the next attempt.

Once the browser session is authenticated, the browser can be used to navigate through the API. Use the links provided in userDefinedFields to navigate through the hierarchy of Address Manager collections and resources. For example, selecting the configurations link will navigate to the /api/v2/configurations endpoint and return a collection of all Address Manager Configurations.

## RESTful v2 API Format

### . HTTP request methods

The Address Manager RESTful v2 API supports the following standard HTTP Request Methods:

* GET 
* POST 
* PUT 
* DELETE 

**Note:**

* Supported methods will vary depending on the endpoint. Refer to the Swagger UI or OAS3 documentation to view supported methods for each endpoint.
* PUT is the primary method for updating resources. PATCH is also used for updating select resource fields. Refer to the Swagger UI or OAS3 documentation to view endpoints that that accept the PATCH method.

### . HTTP response status codes

The Address Manager RESTful v2 API uses the following HTTP response status codes:

#### Success

Status codes indicating a successful response.

| Status Code | Reason |
|-------------|--------|
| 200 | OK |
| 201 | Created |
| 202 | Accepted |
| 204 | No Content |

#### Redirection

Status codes informing the client that its request is being redirected to another URI.

| Status Code | Reason |
|-------------|--------|
| 308 | Permanent Redirect |

#### Client Error

Status codes indicating that the request was not successful due to client error. The client may retry after making the necessary corrections to the request.

| Status Code | Reason |
|-------------|--------|
| 400 | Bad Request |
| 401 | Unauthorized |
| 403 | Forbidden |
| 404 | Not Found |
| 405 | Method Not Allowed |
| 406 | Not Acceptable |
| 409 | Conflict |
| 415 | Unsupported Media Type |
| 429 | Too Many Requests |

#### Server Error

Status codes indicating the request was not successful due to an unexpected or unrecoverable server error.

| Status Code | Reason |
|-------------|--------|
| 500 | Internal Server Error |
| 501 | Not Implemented |

### . HTTP headers

The v9.5.0 Address Manager RESTful v2 API supports the following HTTP headers to provide additional options when creating and updating v2 API resources:

**Note:** The following HTTP headers are not documented in the 9.5.0 RESTful v2 API Swagger UI / OpenAPI document, aside from x-bcn-change-control-comment. Applicable endpoints for undocumented headers are listed in the table below.

| HTTP Header | Used For | Action | Applicable Endpoints |
|-------------|----------|--------|----------------------|
| **x-bcn-change-control-comment** | Adding a change control comment | Adds a change control comment. | Documented in the 9.5.0 RESTful v2 API Swagger UI / OpenAPI document |
| **x-bcn-link-to-external-host** | Creating and updating Alias, MX, and SRV records | (Only when provided with an absolute name) Indicates whether the linked record is an external host. | POST /api/v2/templates/{collectionId}/resourceRecords <br>POST /api/v2/zones/{collectionId}/resourceRecords <br>PUT /api/v2/resourceRecords/{id} |
| **x-bcn-reuse-existing** | Creating IPv4 blocks and networks | Indicates whether preexisting empty ranges will be searched when using the `DEPTH_FIRST` traversal method to determine the starting address of the block/network. | POST /api/v2/blocks/{collectionId}/blocks <br>POST /api/v2/blocks/{collectionId}/networks |
| **x-bcn-traversal-method** | Creating IPv4 blocks and networks | Sets the algorithm used to determine the starting address of the block/network when only a size was provided for the `range` value. | POST /api/v2/blocks/{collectionId}/blocks <br>POST /api/v2/blocks/{collectionId}/networks <br>POST /api/v2/blocks/{collectionId}/imports |
| **x-bcn-no-gateway** | Creating and updating IPv4 networks | Indicates whether the IPv4 network should not contain a gateway address. | POST /api/v2/blocks/{collectionId}/networks <br>POST /api/v2/blocks/{collectionId}/imports <br>PUT /api/v2/networks/{id} |
| **x-bcn-create-reverse-record** | Assigning IPv4/IPv6 addresses | Indicates whether a reverse record should be created for the host. | POST /api/v2/networks/{collectionId}/addresses <br>POST /api/v2/networks/{collectionId}/imports |
| **x-bcn-override-naming-policy** | Creating and updating resource records | Indicates whether to override the naming policy for the view or zone when creating the resource record. | POST /api/v2/networks/{collectionId}/addresses <br>POST /api/v2/networks/{collectionId}/imports <br>POST /api/v2/zones/{collectionId}/imports <br>PUT /api/v2/resourceRecords/{id} <br>POST /api/v2/resourceRecords/{id} <br>POST /api/v2/templates/{collectionId}/resourceRecords <br>POST /api/v2/workflowRequests/{collectionId}/resourceRecords <br>POST /api/v2/zones/{collectionId}/resourceRecords |
| **x-bcn-allow-multi-label-zonenames** | Creating and updating zones | Indicates whether a dotted zone name will be used when an absolute name is specified, instead of creating non-existent subzones. | POST /api/v2/views/{collectionId}/imports <br>PUT /api/v2/views/{collectionId}/imports <br>POST /api/v2/views/{collectionId}/zones <br>POST /api/v2/workflowRequests/{collectionId}/zones <br>POST /api/v2/zones/{collectionId}/zones |
| **x-bcn-allow-address-overlap** | Auto-creation of networks when creating or updating resource records | Indicates whether IP address overlap detection will be overridden for auto-created networks. | POST /api/v2/zones/{collectionId}/imports <br>PUT /api/v2/resourceRecords/{id} <br>POST /api/v2/addresses/{collectionId}/resourceRecords <br>POST /api/v2/templates/{collectionId}/resourceRecords <br>POST /api/v2/workflowRequests/{collectionId}/resourceRecords <br>POST /api/v2/zones/{collectionId}/resourceRecords <br>PATCH /api/v2/workflowRequests/{id} |
| **x-bcn-orphaned-address-state** | Updating DHCPv4 ranges | Indicates the state to assign DHCP allocated IPv4 addresses that are no longer part of the resized range. | DELETE /api/v2/resourceRecords/{id} <br>PUT /api/v2/resourceRecords/{id} |
| **x-bcn-auto-create-network** | Creating and updating resource records | Indicates whether a network will be automatically created if a network containing the IP address or addresses specified in the resource record does not already exist. | POST /api/v2/zones/{collectionId}/imports <br>PUT /api/v2/resourceRecords/{id} <br>POST /api/v2/addresses/{collectionId}/resourceRecords <br>POST /api/v2/templates/{collectionId}/resourceRecords <br>POST /api/v2/zones/{collectionId}/resourceRecords |
| **x-bcn-same-as-zone** | Creating and updating resource records | Indicates whether the zone name will be used for the resource record name. | POST /api/v2/zones/{collectionId}/imports <br>PUT /api/v2/resourceRecords/{id} <br>POST /api/v2/workflowRequests/{collectionId}/resourceRecords <br>POST /api/v2/zones/{collectionId}/resourceRecords |
| **x-bcn-reset-services** | Updating DNS/DHCP Servers | Indicates whether to reset configurations for DNS, DHCP, and TFTP services on the DNS/DHCP Server. Refer to the Swagger documentation for more information. | PUT /api/v2/servers/{id} |
| **x-bcn-reset-replication** | Removing Address Manager servers from replication clusters | Indicates whether to reset replication on the Address Manager server, returning the server to its original stand-alone state. | DELETE /api/v2/databases/{collectionId}/servers/{id} |
| **x-bcn-force-failover** | Updating Address Manager servers in replication clusters | Indicates whether to initiate failover on the primary Address Manager server in the database replication cluster. | PATCH /api/v2/databases/{collectionId}/servers/{id} |
| **x-bcn-force-undo** | Undoing transactions | Indicates whether to force undo a transaction if the undo operation is blocked due to broken optional resource dependencies. | POST /api/v2/transactions |

### . Supported media types

The Address Manager RESTful v2 API supports a variety of media types depending on the operation.

Specify a response media type by adding an Accept HTTP header to each request message. If the client sends a request header of Accept: `*/*` (no media type specified), the default response media type is `application/hal+json`. For POST and PUT operations, specify the media type of the payload with the Content-Type header.

**Note:** Browsers by default will negotiate a `text/html` media type. As such, API responses will be returned with a Content-Type of `text/html`, not `application/hal+json`.

| Operation | Accepts | Produces |
|-----------|---------|----------|
| **GET single resource** | - | `application/hal+json` <br>`application/json` <br>`text/html` <br>`application/octet-stream` |
| **GET collection** | - | `application/hal+json` <br>`application/json` <br>`text/html` <br>`text/csv` |
| **POST/PUT** | `application/hal+json` <br>`application/json` <br>`multipart/form-data` | `application/hal+json` <br>`application/json` |
| **PATCH** | `application/merge-patch+json` | `application/hal+json` <br>`application/json` |

## Resource representation

### . Resources

The RESTful v2 API presents Address Manager objects as resources. Each resource has a unique URI or endpoint composed of the resource's collection name and ID (unique to the resource type). For example, a HostRecord resource with ID 1234 would have a URI of `/resourceRecords/1234`. Resources, defined by their fields, are retrieved and mutated by sending requests to resource or collection endpoints using the standard HTTP methods: GET, POST, PUT, PATCH and DELETE. To fetch an individual resource, a GET request is sent to the resource's endpoint. The body of the response message for a GET request will contain a representation of a resource. The representation contains all fields describing the complete state of an Address Manager object.

**Attention:** For resources provided in request bodies, the Address Manager RESTful v2 API ignores unknown fields and will not throw an error if included. Only the expected fields detailed in the resource schemas are validated.

#### Common resource fields

The following fields are common to all resource representations:

* **id** - (number) Identifier of resource.
* **type** - (string) Type of resource.
* **name** - (string) Name of resource.
* **\_links** - (object) if media type `application/hal+json` is specified, the URI link to the resource and links to relevant collections. Refer to HAL links for more information.
 * **self.href** - (string) URI of resource.
 * **collection.href** - (string) URI of the collection the resource is a member of. If the resource is not a member of a collection, this property can be omitted.
 * **up.href** - (string) URI of the parent resource. If the resource is not within a hierarchy of resources, this property can be omitted.
 * **other \_links** - (string) additional URI links to associated subcollections.

#### Example View resource

**Request**
```http
GET http://{Address_Manager_IP}/api/v2/views/101148
Authorization: Basic {basicAuthenticationCredentials}
```

**Response**
```http
HTTP/1.1 200 OK
Content-Type: application/hal+json

{
 "id": 101148,
 "type": "View",
 "name": "Default",
 "configuration": {
 "id": 100881,
 "type": "Configuration",
 "name": "config-1",
 "_links": {
 "self": {
 "href": "/api/v2/configurations/100881"
 }
 }
 },
 "deviceRegistrationEnabled": false,
 "deviceRegistrationPortalAddress": null,
 "userDefinedFields": null,
 "_links": {
 "self": {
 "href": "/api/v2/views/101148"
 },
 "collection": {
 "href": "/api/v2/configurations/100881/views"
 },
 "up": {
 "href": "/api/v2/configurations/100881"
 },
 "deploymentOptions": {
 "href": "/api/v2/views/101148/deploymentOptions"
 },
 "deploymentRoles": {
 "href": "/api/v2/views/101148/deploymentRoles"
 },
 "restrictedRanges": {
 "href": "/api/v2/views/101148/restrictedRanges"
 },
 "namingPolicies": {
 "href": "/api/v2/views/101148/namingPolicies"
 },
 "templates": {
 "href": "/api/v2/views/101148/templates"
 },
 "zones": {
 "href": "/api/v2/views/101148/zones"
 },
 "tags": {
 "href": "/api/v2/views/101148/tags"
 },
 "accessRights": {
 "href": "/api/v2/views/101148/accessRights"
 },
 "transactions": {
 "href": "/api/v2/views/101148/transactions"
 },
 "userDefinedLinks": {
 "href": "/api/v2/views/101148/userDefinedLinks"
 }
 }
}
```

### Collections

Related resources are grouped in collections. To fetch all resources in a collection, a GET request is sent to the collection endpoint. To create a resource, a POST request is sent to the collection endpoint. The body of the POST request will be a resource (JSON) containing at least the minimum required fields for creating the desired resource.

Use the pagination query parameters `offset` and `limit` to determine which and how many resources will be returned in a single response. Refer to Pagination for more information.

#### Common collection fields

The following fields are common to all collections of resources:

* **count** - (number) The number of resources returned in the collection.
* **\_links** - (object) URI links to the previous and next page of resources in the collection. If no offset is set and the number of resources returned is less than the limit, this property can be omitted.
* **data** - (array) An array of the resources returned.

#### Example collection of IPv4 Network resources

**Request**
```http
GET http://{Address_Manager_IP}/api/v2/networks?limit=3&offset=5
Authorization: Basic {basicAuthenticationCredentials}
```

**Response**
```http
HTTP/1.1 200 OK
Content-Type: application/hal+json

{
 "count": 3,
 "_links": {
 "prev": {
 "href": "/api/v2/blocks/101115/networks?offset=2&limit=3"
 },
 "next": {
 "href": "/api/v2/blocks/101115/networks?offset=8&limit=3"
 }
 },
 "data": [
 {
 "id": 101126,
 "type": "IPv4Network",
 "name": null,
 "configuration": {
 "id": 100881,
 "type": "Configuration",
 "name": "config-1",
 "_links": {
 "self": {
 "href": "/api/v2/configurations/100881"
 }
 }
 },
 "range": "10.0.5.0/24",
 "_links": {
 "self": {
 "href": "/api/v2/networks/101126"
 },
 "collection": {
 "href": "/api/v2/blocks/101115/networks"
 },
 "up": {
 "href": "/api/v2/blocks/101115"
 },
 "addresses": {
 "href": "/api/v2/networks/101126/addresses"
 },
 "defaultZones": {
 "href": "/api/v2/networks/101126/defaultZones"
 }
 }
 },
 {
 "id": 101128,
 "type": "IPv4Network",
 "name": null,
 "configuration": {
 "id": 100881,
 "type": "Configuration",
 "name": "config-1",
 "_links": {
 "self": {
 "href": "/api/v2/configurations/100881"
 }
 }
 },
 "range": "10.0.6.0/24",
 "_links": {
 "self": {
 "href": "/api/v2/networks/101128"
 },
 "collection": {
 "href": "/api/v2/blocks/101115/networks"
 },
 "up": {
 "href": "/api/v2/blocks/101115"
 },
 "addresses": {
 "href": "/api/v2/networks/101128/addresses"
 },
 "defaultZones": {
 "href": "/api/v2/networks/101128/defaultZones"
 }
 }
 },
 {
 "id": 101130,
 "type": "IPv4Network",
 "name": null,
 "configuration": {
 "id": 100881,
 "type": "Configuration",
 "name": "config-1",
 "_links": {
 "self": {
 "href": "/api/v2/configurations/100881"
 }
 }
 },
 "range": "10.0.7.0/24",
 "_links": {
 "self": {
 "href": "/api/v2/networks/101130"
 },
 "collection": {
 "href": "/api/v2/blocks/101115/networks"
 },
 "up": {
 "href": "/api/v2/blocks/101115"
 },
 "addresses": {
 "href": "/api/v2/networks/101130/addresses"
 },
 "defaultZones": {
 "href": "/api/v2/networks/101130/defaultZones"
 }
 }
 }
 ]
}
```

### . Errors

#### Common error fields

The following fields are common to all error responses:

* **status** - (number) HTTP status code of error (400-599).
* **reason** - (string) Reason phrase of status code.
* **code** - (string) API error code.
* **message** - (string) Description of API error code.

#### Example error response

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{
 "status": 401,
 "reason": "Unauthorized",
 "code": "InvalidAuthorizationToken",
 "message": "The provided authorization token is invalid"
}
```

### . HAL links

A key constraint of the REST architectural style is HATEOAS or Hypermedia as the Engine of Application State. The v2 RESTful API implements this constraint by embedding a `_links` object in the JSON representation of resources. These links are used to navigate through Address Manager's hierarchy of resources, as well as mutate these resources, without having to know the inherent structure of the hierarchy.

The `_links` object abides by the Hypermedia Application Language or HAL draft IETF standard and is included in JSON representations when the media type `application/hal+json` or `*/*` is set in the Accept header of the HTTP request. A media type of `application/json` will exclude the `_links` field in resource representations.

Note that the `_links` field is considered metadata and is never a required field in POST or PUT request bodies.

#### Using HAL links

The example configuration resource below contains links for collections associated with the configuration. To create a view resource for this configuration, a POST request can be made using the `views` link as the destination resource: `_links.views.href` (`/api/v2/configurations/100881/views` in this instance).

#### Example Configuration resource with HAL links

**Request**
```http
GET http://{Address_Manager_IP}/api/v2/configurations/100881
Authorization: Basic {basicAuthenticationCredentials}
```

**Response**
```http
HTTP/1.1 200 OK
Content-Type: application/hal+json

{
 "id": 100881,
 "type": "Configuration",
 "name": "config-1",
 "description": null,
 "configurationGroup": null,
 "_links": {
 "self": {
 "href": "/api/v2/configurations/100881"
 },
 "collection": {
 "href": "/api/v2/configurations"
 },
 "up": {
 "href": "/api/v2/1"
 },
 "accessControlLists": {
 "href": "/api/v2/configurations/100881/accessControlLists"
 },
 "blocks": {
 "href": "/api/v2/configurations/100881/blocks"
 },
 "clientClasses": {
 "href": "/api/v2/configurations/100881/clientClasses"
 },
 "clientIdentifiers": {
 "href": "/api/v2/configurations/100881/clientIdentifiers"
 },
 "deploymentOptions": {
 "href": "/api/v2/configurations/100881/deploymentOptions"
 },
 "deploymentOptionDefinitions": {
 "href": "/api/v2/configurations/100881/deploymentOptionDefinitions"
 },
 "devices": {
 "href": "/api/v2/configurations/100881/devices"
 },
 "macAddresses": {
 "href": "/api/v2/configurations/100881/macAddresses"
 },
 "macPools": {
 "href": "/api/v2/configurations/100881/macPools"
 },
 "merges": {
 "href": "/api/v2/configurations/100881/merges"
 },
 "realms": {
 "href": "/api/v2/configurations/100881/realms"
 },
 "reconciliationPolicies": {
 "href": "/api/v2/configurations/100881/reconciliationPolicies"
 },
 "responsePolicies": {
 "href": "/api/v2/configurations/100881/responsePolicies"
 },
 "servers": {
 "href": "/api/v2/configurations/100881/servers"
 },
 "serverGroups": {
 "href": "/api/v2/configurations/100881/serverGroups"
 },
 "signingKeys": {
 "href": "/api/v2/configurations/100881/signingKeys"
 },
 "splits": {
 "href": "/api/v2/configurations/100881/splits"
 },
 "templates": {
 "href": "/api/v2/configurations/100881/templates"
 },
 "tftpGroups": {
 "href": "/api/v2/configurations/100881/tftpGroups"
 },
 "views": {
 "href": "/api/v2/configurations/100881/views"
 },
 "workflowRequests": {
 "href": "/api/v2/configurations/100881/workflowRequests"
 },
 "zoneGroups": {
 "href": "/api/v2/configurations/100881/zoneGroups"
 },
 "tags": {
 "href": "/api/v2/configurations/100881/tags"
 },
 "accessRights": {
 "href": "/api/v2/configurations/100881/accessRights"
 },
 "transactions": {
 "href": "/api/v2/configurations/100881/transactions"
 }
 }
}
```

## Query parameters

The Address Manager RESTful v2 API uses query parameters to modify the responses returned from GET requests. You can use query parameters to filter results based on set criteria, return specified fields from a resource, order the results based on set criteria, or paginate through results for large data sets.

**Attention:** The Address Manager RESTful v2 API ignores unknown query parameters and proceeds to return results based on the original valid API call, along with any valid query parameters configured.

### . Referencing fields

The RESTful v2 API uses dot notation for field paths when using the `filter`, `fields`, and `ordering` query parameters.

For example, the User `id` field in the following UserSession resource can be referenced with `user.id`:
```json
{
 "id": 36,
 "type": "UserSession",
 "state": "LOGGED_IN",
 "user": {
 "id": 3,
 "type": "User",
 "name": "admin",
 "_links": {
 "self": {
 "href": "/api/v2/users/3"
 }
 }
 }
}
```

### . Filter

The RESTful v2 API supports results filtering using the `filter` query parameter.

The value supplied to the filter parameter is a list of field predicates using the API's filter grammar:
```
filter=<field>:operator(value)
```

For example, the following filter string will instruct the API to filter User resources with names containing the string 'bc':
```http
GET http://{Address_Manager_IP}/api/v2/users?filter=name:contains('bc')
```

In this example `contains()` is a filter operator. The list of supported operators is specific to the resource field.

#### Supported filter operators:

| Operator | Description | Field Types |
|----------|-------------|-------------|
| eq | Equals | numbers, strings, addresses, dates, enums, booleans, ranges |
| ne | Not equals | numbers, strings, addresses, enums, booleans |
| ge | Greater than equals | numbers, dates, addresses, ranges |
| gt | Greater than | numbers, dates, addresses, ranges |
| le | Less than equals | numbers, dates, addresses, ranges |
| lt | Less than | numbers, dates, addresses, ranges |
| contains | Contains | strings, ranges |
| startsWith | Starts with | strings, ranges |
| endsWith | Ends with | strings |
| in | Match a list of values | numbers, strings, enums, booleans, addresses |

#### Supported filter fields:

The RESTful v2 API currently supports a variety of filterable fields for each resource type. Each release adds support for additional filterable fields, targeting an ultimate goal of filter support for all resource fields where feasible. If an unsupported field is provided with the `filter` parameter, the API will respond with a `400 InvalidFilterField` error and a list of supported filter fields for that endpoint.

**Note:** `address` and `range` fields are strings with special handling to allow comparison. When filtering by address fields, the value provided must also be an address. The following example retrieves Addresses greater than 192.168.0.10 for a specified Network:
```http
GET http://{Address_Manager_IP}/api/v2/networks/{collectionId}/addresses?filter=address:gt("192.168.0.10")
```

When filtering by range fields, the value provided when using the `eq`, `ge`, `gt`, `le`, and `lt` operators must be a range. The `eq` operator accepts ranges in the form of a CIDR length (`eq("/16")`), address and CIDR length (`eq("192.168.0.0/16")`), or address range (`eq("192.168.0.0-192.168.0.255")`). The `eq` operator will return resources that match the provided range value exactly, therefore filtering by CIDR length only will return all resources matching the CIDR length, while the inclusion of an address will return only resources matching both address and length. The following example will return all blocks with a CIDR length of 24:
```http
GET http://{Address_Manager_IP}/api/v2/blocks?filter=range:eq("/24")
```

The `ge`, `gt`, `le`, and `lt` operators accept either CIDR length (`gt("/16")`) or address and CIDR length (`gt("192.168.0.0/16")`) for the range value, and will return results based on size comparison of the CIDR length. If only a CIDR length is provided, both IPv4 and IPv6 resources that meet the size comparison criteria will be returned. If an address and CIDR length is provided, the resources returned will match the address protocol type (however unlike `eq`, resources returned are not limited to the exact address). The following example will return all IPv4 Blocks that are greater than or equal to CIDR length 16:
```http
GET http://{Address_Manager_IP}/api/v2/blocks?filter=range:ge("192.168.0.0/16")
```

The `contains` and `startsWith` operators are also supported for range fields, by providing an address for the value. The following example will return all IPv4 Networks that contain the address 10.0.0.5:
```http
GET http://{Address_Manager_IP}/api/v2/networks?filter=range:contains("10.0.0.5")
```

#### Combination of filter predicates

Filter predicates can be combined to form more complex filters using the `and` and `or` operators:

Retrieve Transactions with a `creationDateTime` greater than '2022-01-10T14:14:45Z' and less than '2022-01-20T14:14:45Z' 
```http
GET http://{Address_Manager_IP}/api/v2/transactions?filter=creationDateTime:ge('2022-01-10T14:14:45Z') and creationDateTime:le('2022-01-20T14:14:45Z')
```

#### Additional examples:

Retrieve all Users with a name equal to 'admin1' (implied eq) 
```http
GET http://{Address_Manager_IP}/api/v2/users?filter=name:'admin1'
```

Retrieve all Addresses greater than or equal to '192.168.0.0' and less than or equal to '192.168.0.255' 
```http
GET http://{Address_Manager_IP}/api/v2/addresses?filter=address:ge('192.168.0.0') and address:le('192.168.0.255')
```

Retrieve all Networks with a value of `true` for the `pingBeforeAssignEnabled` field.
```http
GET http://{Address_Manager_IP}/api/v2/networks?filter=pingBeforeAssignEnabled:eq(true)
```

Retrieve all Blocks with a name that contains 'UK' or 'FR' 
```http
GET http://{Address_Manager_IP}/api/v2/blocks?filter=name:contains('UK') or name:contains('FR')
```

Retrieve all Blocks with a `configuration.name` equal to 'config-2' or 'config-3' 
```http
GET http://{Address_Manager_IP}/api/v2/blocks?filter=configuration.name:in('config-2', 'config-3')
```

Retrieve all Addresses in a Network with a state equal to 'RESERVED' or 'DHCP\_RESERVED' 
```http
GET http://{Address_Manager_IP}/api/v2/networks/{Network_ID}/addresses?filter=state:in('RESERVED', 'DHCP_RESERVED')
```

Retrieve all Networks that are immediate children of a Block 
```http
GET http://{Address_Manager_IP}/api/v2/blocks/{Block_ID}/networks
```

Retrieve all Networks that are children of a '10.0.0.0/8' Block within Configuration 'config0', including children of sub-blocks.
```http
GET http://{Address_Manager_IP}/api/v2/networks?filter=configuration.name:'config0' and range:startsWith('10.')
```

### . Fields

By default, all fields of a resource representation are returned in a response to a GET request. To limit the number of fields returned, the `fields` query parameter can be used in one of two ways.

To request a subset of fields, supply the `fields` query parameter with a list of field names. For example, the following request instructs the API to return the `id`, `type`, `name`, and `range` fields of Network resources in the global collection. It also returns the `id` and `name` fields of each Network resource's inlined Configuration resource.

**Request:**
```http
GET http://{Address_Manager_IP}/api/v2/networks?fields=id,type,name,range,configuration.id,configuration.name
Authorization: Basic {basicAuthenticationCredentials}
```

**Response:**
```http
HTTP/1.1 200 OK
Content-Type: application/hal+json

{
 "count": 2,
 "data": [
 {
 "id": 100922,
 "type": "IPv6Network",
 "name": "My IPv6 Network",
 "configuration": {
 "id": 100881,
 "name": "Default"
 },
 "range": "2A00:23C6:A890:5001::/64"
 },
 {
 "id": 100923,
 "type": "IPv4Network",
 "name": "My Home Network",
 "configuration": {
 "id": 100881,
 "name": "Default"
 },
 "range": "192.168.1.0/24"
 }
 ]
}
```

Alternatively, a request can specify only the fields it does not want included in the resource representation using the `not` operator. The following request instructs the API to return all fields for View resources of a particular Configuration except for the `id` and `_links` fields.
```http
GET http://{Address_Manager_IP}/api/v2/configurations/100882/views?fields=not(id,_links)
```

#### . Embedding subcollections

Most resources have subcollections. For example, Zone resources have a `resourceRecords` subcollection containing all resource records in that Zone. To reduce the number of API calls when fetching resources and their subcollections, the `embed()` operator can be used to embed subcollections. The following will instruct the API to in-line the `resourceRecords` subcollection under the `_embedded` field of a Zone resource.

**Request**
```http
GET http://{Address_Manager_IP}/api/v2/zones/100927/zones?fields=embed(resourceRecords)
Authorization: Basic {basicAuthenticationCredentials}
```

**Response**
```http
HTTP/1.1 200 OK
Content-Type: application/hal+json

{
 "count": 1,
 "data": [
 {
 "id": 100928,
 "type": "Zone",
 "name": "bluecatlabs",
 "configuration": {
 "id": 100898,
 "type": "Configuration",
 "name": "config-1",
 "_links": {
 "self": {
 "href": "/api/v2/configurations/100898"
 }
 }
 },
 "absoluteName": "bluecatlabs.com",
 "_links": {
 "self": {
 "href": "/api/v2/zones/100928"
 },
 "collection": {
 "href": "/api/v2/zones/100927/zones"
 },
 "up": {
 "href": "/api/v2/zones/100927"
 },
 "resourceRecords": {
 "href": "/api/v2/zones/100928/resourceRecords"
 },
 "zones": {
 "href": "/api/v2/zones/100928/zones"
 }
 },
 "_embedded": {
 "resourceRecords": [
 {
 "id": 100933,
 "type": "HostRecord",
 "name": "bam",
 "configuration": {
 "id": 100898,
 "type": "Configuration",
 "name": "config-1",
 "_links": {
 "self": {
 "href": "/api/v2/configurations/100898"
 }
 }
 },
 "absoluteName": "bam.bluecatlabs.com",
 "_links": {
 "self": {
 "href": "/api/v2/resourceRecords/100933"
 },
 "collection": {
 "href": "/api/v2/zones/100928/resourceRecords"
 },
 "up": {
 "href": "/api/v2/zones/100928"
 },
 "addresses": {
 "href": "/api/v2/resourceRecords/100933/addresses"
 },
 "dependentRecords": {
 "href": "/api/v2/resourceRecords/100933/dependentRecords"
 }
 },
 "_embedded": {}
 }
 ]
 }
 }
 ]
}
```

Specifying a field path will recursively embed subcollections. The following fetch will embed the `resourceRecords` subcollection and for each resource record embed their `addresses` subcollection:

**Request**
```http
GET http://{Address_Manager_IP}/api/v2/zones/100927/zones?fields=embed(resourceRecords.addresses)
Authorization: Basic {basicAuthenticationCredentials}
```

**Response**
```http
HTTP/1.1 200 OK
Content-Type: application/hal+json

{
 "count": 1,
 "data": [
 {
 "id": 100928,
 "type": "Zone",
 "name": "bluecatlabs",
 "configuration": {
 "id": 100898,
 "type": "Configuration",
 "name": "config-1",
 "_links": {
 "self": {
 "href": "/api/v2/configurations/100898"
 }
 }
 },
 "absoluteName": "bluecatlabs.com",
 "_links": {
 "self": {
 "href": "/api/v2/zones/100928"
 },
 "collection": {
 "href": "/api/v2/zones/100927/zones"
 },
 "up": {
 "href": "/api/v2/zones/100927"
 },
 "resourceRecords": {
 "href": "/api/v2/zones/100928/resourceRecords"
 },
 "zones": {
 "href": "/api/v2/zones/100928/zones"
 }
 },
 "_embedded": {
 "resourceRecords": [
 {
 "id": 100933,
 "type": "HostRecord",
 "name": "bam",
 "configuration": {
 "id": 100898,
 "type": "Configuration",
 "name": "config-1",
 "_links": {
 "self": {
 "href": "/api/v2/configurations/100898"
 }
 }
 },
 "absoluteName": "bam.bluecatlabs.com",
 "_links": {
 "self": {
 "href": "/api/v2/resourceRecords/100933"
 },
 "collection": {
 "href": "/api/v2/zones/100928/resourceRecords"
 },
 "up": {
 "href": "/api/v2/zones/100928"
 },
 "addresses": {
 "href": "/api/v2/resourceRecords/100933/addresses"
 },
 "dependentRecords": {
 "href": "/api/v2/resourceRecords/100933/dependentRecords"
 }
 },
 "_embedded": {
 "addresses": [
 {
 "id": 100932,
 "type": "IPv4Address",
 "name": null,
 "configuration": {
 "id": 100898,
 "type": "Configuration",
 "name": "config-1",
 "_links": {
 "self": {
 "href": "/api/v2/configurations/100898"
 }
 }
 },
 "address": "192.168.1.15",
 "_links": {
 "self": {
 "href": "/api/v2/addresses/100932"
 },
 "collection": {
 "href": "/api/v2/networks/100930/addresses"
 },
 "up": {
 "href": "/api/v2/networks/100930"
 },
 "leases": {
 "href": "/api/v2/addresses/100932/leases"
 },
 "resourceRecords": {
 "href": "/api/v2/addresses/100932/resourceRecords"
 }
 },
 "_embedded": {}
 }
 ]
 }
 }
 ]
 }
 }
 ]
}
```

### . Ordering

Customize the order of resources returned by using the `orderBy` query parameter. By default, the order direction will be in ascending order. The order direction can be set using the `asc()` and `desc()` operators. The following request fetches all IPv4/IPv6 blocks and sub blocks, and orders the result by block name in descending order.
```http
GET http://{Address_Manager_IP}/api/v2/blocks?orderBy=desc(name)
```

| Name | Purpose | Syntax | Operators | Examples |
|------|---------|--------|-----------|----------|
| orderBy | Results ordering | `orderBy=<field>` | • `asc` <br>• `desc` | • `orderBy=desc(id)` <br>• `orderBy=asc(name)` |

### . Pagination

By default, the RESTful v2 API will return up to 1000 resources starting at the first row of the result set. If the total resource count is larger than the default limit, requests can use the `limit` and `offset` query parameters to page through the complete list.

The `count` field is set to the number of resources returned. To facilitate iteration, `prev` and `next` links are included when the total resource count exceeds the specified limit. The `data` field is set to an array containing the list of resources. If no resources were found matching the request, an empty array is returned.

The maximum value for limit is 100,000.

**Request**
```http
GET http://{Address_Manager_IP}/api/v2/locations?limit=2000&offset=1000
Authorization: Basic {basicAuthenticationCredentials}
```

**Response**
```http
HTTP/1.1 200 OK
Content-Type: application/hal+json

{
 "count": 2000,
 "_links": {
 "prev": {
 "href": "/api/v2/locations?offset=0&limit=1000"
 },
 "next": {
 "href": "/api/v2/locations?offset=3000&limit=2000"
 }
 },
 "data": [
 ...
 ]
}
```

| Name | Purpose | Syntax | Operators | Examples |
|------|---------|--------|-----------|----------|
| offset | Pagination: Resource (row) offset | `offset=<row number>` | - | `offset=10` |
| limit | Pagination: Result set max count | `limit=<count>` | - | `limit=1000` |

## RESTful v2 API examples

### . Basic operations

#### . Creating resources

Resources are created by sending a POST request to a collection endpoint. The body of the request will be a resource (JSON) containing at least the minimum required fields for creating the desired resource. The following example creates a Configuration resource named `Warehouse` belonging to the Configuration Group `West Coast`. `name` is the only required field when creating a Configuration resource but any field can be specified to initialize the resource. Fields not set by the client will be given default values by the API. If the POST request is successful, a representation of the newly created Configuration resource is returned. The complete state of the resource is returned.

**Attention:** For resources provided in request bodies, the Address Manager RESTful v2 API ignores unknown fields and will not throw an error if included. Only the expected fields detailed in the resource schemas are validated.

**Request**
```http
POST http://{Address_Manager_IP}/api/v2/configurations
Authorization: Basic {basicAuthenticationCredentials}
Content-Type: application/hal+json

{
 "name": "Warehouse",
 "configurationGroup": "West Coast"
}
```

**Response**
```http
HTTP/1.1 201 Created
Content-Type: application/hal+json

{
 "id": 100934,
 "type": "Configuration",
 "name": "Warehouse",
 "description": null,
 "configurationGroup": "West Coast",
 "_links": {
 "self": {
 "href": "/api/v2/configurations/100934"
 },
 "collection": {
 "href": "/api/v2/configurations"
 },
 "up": {
 "href": "/api/v2/1"
 },
 "accessControlLists": {
 "href": "/api/v2/configurations/100934/accessControlLists"
 },
 "blocks": {
 "href": "/api/v2/configurations/100934/blocks"
 }
 }
}
```

#### . Retrieving resources

**Retrieving a collection of resources**

Retrieve a collection of resources by sending a GET request to a collection endpoint.

**Request**
```http
GET http://{Address_Manager_IP}/api/v2/configurations
Authorization: Basic {basicAuthenticationCredentials}
```

**Response**
```http
HTTP/1.1 200 OK
Content-Type: application/hal+json

{
 "count": 2,
 "data": [
 {
 "id": 100946,
 "type": "Configuration",
 "name": "config-1",
 "description": null,
 "configurationGroup": null,
 "_links": {
 "self": {
 "href": "/api/v2/configurations/100946"
 },
 "collection": {
 "href": "/api/v2/configurations"
 },
 "up": {
 "href": "/api/v2/1"
 },
 "accessControlLists": {
 "href": "/api/v2/configurations/100946/accessControlLists"
 },
 "blocks": {
 "href": "/api/v2/configurations/100946/blocks"
 }
 }
 },
 {
 "id": 100958,
 "type": "Configuration",
 "name": "config-2",
 "description": null,
 "configurationGroup": null,
 "_links": {
 "self": {
 "href": "/api/v2/configurations/100958"
 },
 "collection": {
 "href": "/api/v2/configurations"
 },
 "up": {
 "href": "/api/v2/1"
 },
 "accessControlLists": {
 "href": "/api/v2/configurations/100958/accessControlLists"
 },
 "blocks": {
 "href": "/api/v2/configurations/100958/blocks"
 }
 }
 }
 ]
}
```

**Retrieving a single resource**

Retrieve a single resource by sending a GET request to the resources URI.

**Tip:** A resource's URI can be found in its `_links.self.href` field when the response media type is `application/json+hal`.

**Request**
```http
GET http://{Address_Manager_IP}/api/v2/configurations/100946
Authorization: Basic {basicAuthenticationCredentials}
```

**Response**
```http
HTTP/1.1 200 OK
Content-Type: application/hal+json

{
 "id": 100946,
 "type": "Configuration",
 "name": "config-1",
 "description": null,
 "configurationGroup": null,
 "_links": {
 "self": {
 "href": "/api/v2/configurations/100946"
 },
 "collection": {
 "href": "/api/v2/configurations"
 },
 "up": {
 "href": "/api/v2/1"
 },
 "accessControlLists": {
 "href": "/api/v2/configurations/100946/accessControlLists"
 },
 "blocks": {
 "href": "/api/v2/configurations/100946/blocks"
 }
 }
}
```

#### . Updating resources

To update a resource, a PUT request is sent to the URI of the resource to be updated. The body of the PUT request must contain the complete representation of the resource.

**Tip:**
* A resource's URI can be found in its `_links.self.href` field when the response media type is `application/json+hal`.
* The `_links` field is considered metadata and is not required for PUT request bodies.

In the following example, a GET request is sent to the URI for a Resource Record resource. The resource received from the GET request is then sent back to the same URI in a PUT request, with the `name` field modified from "bc1" to "bc2". The API responds with a 200 OK status code and the updated resource.

**Request**
```http
GET http://{Address_Manager_IP}/api/v2/resourceRecords/100980
Authorization: Basic {basicAuthenticationCredentials}
```

**Response**
```http
HTTP/1.1 200 OK
Content-Type: application/hal+json

{
 "id": 100980,
 "type": "HostRecord",
 "name": "bc1",
 "configuration": {
 "id": 100946,
 "type": "Configuration",
 "name": "config-1",
 "_links": {
 "self": {
 "href": "/api/v2/configurations/100946"
 }
 }
 },
 "absoluteName": "bc1.bluecatlabs.com",
 "_links": {
 "self": {
 "href": "/api/v2/resourceRecords/100980"
 },
 "collection": {
 "href": "/api/v2/zones/100976/resourceRecords"
 },
 "up": {
 "href": "/api/v2/zones/100976"
 },
 "addresses": {
 "href": "/api/v2/resourceRecords/100980/addresses"
 },
 "dependentRecords": {
 "href": "/api/v2/resourceRecords/100980/dependentRecords"
 }
 }
}
```

**Request**
```http
PUT http://{Address_Manager_IP}/api/v2/resourceRecords/100980
Authorization: Basic {basicAuthenticationCredentials}
Content-Type: application/hal+json

{
 "id": 100980,
 "type": "HostRecord",
 "name": "bc2",
 "configuration": {
 "id": 100946,
 "type": "Configuration",
 "name": "config-1",
 "_links": {
 "self": {
 "href": "/api/v2/configurations/100946"
 }
 }
 },
 "absoluteName": "bc1.bluecatlabs.com",
 "_links": {
 "self": {
 "href": "/api/v2/resourceRecords/100980"
 },
 "collection": {
 "href": "/api/v2/zones/100976/resourceRecords"
 },
 "up": {
 "href": "/api/v2/zones/100976"
 },
 "addresses": {
 "href": "/api/v2/resourceRecords/100980/addresses"
 },
 "dependentRecords": {
 "href": "/api/v2/resourceRecords/100980/dependentRecords"
 }
 }
}
```

**Response**
```http
HTTP/1.1 200 OK
Content-Type: application/hal+json

{
 "id": 100980,
 "type": "HostRecord",
 "name": "bc2",
 "configuration": {
 "id": 100946,
 "type": "Configuration",
 "name": "config-1",
 "_links": {
 "self": {
 "href": "/api/v2/configurations/100946"
 }
 }
 },
 "absoluteName": "bc2.bluecatlabs.com",
 "_links": {
 "self": {
 "href": "/api/v2/resourceRecords/100980"
 },
 "collection": {
 "href": "/api/v2/zones/100976/resourceRecords"
 },
 "up": {
 "href": "/api/v2/zones/100976"
 },
 "addresses": {
 "href": "/api/v2/resourceRecords/100980/addresses"
 },
 "dependentRecords": {
 "href": "/api/v2/resourceRecords/100980/dependentRecords"
 }
 }
}
```

#### . Deleting resources

Resources can be deleted by sending a DELETE request to the resource's URI.

**Tip:** A resource's URI can be found in its `_links.self.href` field when the response media type is `application/json+hal`.

**Request**
```http
DELETE http://{Address_Manager_IP}/api/v2/blocks/100975
Authorization: Basic {basicAuthenticationCredentials}
```

**Response**
```http
HTTP/1.1 204 No Content
```

## v1 REST API to RESTful v2 API migration guide

The following section lists the Address Manager RESTv1 API endpoints in alphabetical order and the equivalent RESTful v2 endpoint that can be used to perform a similar operation to help you migrate your current integrations to use the RESTful v2 API. You can click one of the following links to navigate to the relevant table based on the RESTv1 API endpoint that you are looking for:

* [A-F](#a-f-api-endpoints) 
* [G-L](#g-l-api-endpoints) 
* [M-R](#m-r-api-endpoints) 
* [S-Z](#s-z-api-endpoints) 

### A-F API endpoints

| RESTv1 API | RESTv2 Endpoint | Notes |
|-------------|----------------|-------|
| POST /Services/REST/v1/addACL | POST /api/v2/configurations/{collectionId}/accessControlLists | |
| POST /Services/REST/v1/addAccessRight | POST /api/v2/accessRights | |
| POST /Services/REST/v1/addAliasRecord | POST /api/v2/zones/{collectionId}/resourceRecords | |
| POST /Services/REST/v1/addBulkHostRecord | To be implemented in 9.6 | This will be implemented with POST /networks/{collectionId}/imports |
| POST /Services/REST/v1/addCustomOptionDefinition | POST /api/v2/configurations/{collectionId}/deploymentOptionDefinitions | |
| POST /Services/REST/v1/addDHCP4Range | POST /api/v2/networks/{collectionId}/ranges | |
| POST /Services/REST/v1/addDHCP4RangeBySize | POST /api/v2/networks/{collectionId}/ranges | "range": "\<offset>,\<size>" <br>"range": "\<offset>,\<percentage>" |
| POST /Services/REST/v1/addDHCP6ClientDeploymentOption | POST /api/v2/{collection}/{collectionId}/deploymentOptions | |
| POST /Services/REST/v1/addDHCP6Range | POST /api/v2/networks/{collectionId}/ranges | |
| POST /Services/REST/v1/addDHCP6RangeBySize | POST /api/v2/networks/{collectionId}/ranges | "range": "\<offset>,\<size>" <br>"range": "\<offset>,\<percentage>" <br>"range": "/\<prefix length>" |
| POST /Services/REST/v1/addDHCP6ServiceDeploymentOption | POST /api/v2/{collection}/{collectionId}/deploymentOptions | |
| POST /Services/REST/v1/addDHCPClientDeploymentOption | POST /api/v2/{collection}/{collectionId}/deploymentOptions | |
| POST /Services/REST/v1/addDHCPDeploymentRole | POST /api/v2/{collection}/{collectionId}/deploymentRoles | |
| POST /Services/REST/v1/addDHCPMatchClass | POST /api/v2/configurations/{collectionId}/clientClasses | |
| POST /Services/REST/v1/addDHCPServiceDeploymentOption | POST /api/v2/{collection}/{collectionId}/deploymentOptions | |
| POST /Services/REST/v1/addDHCPSubClass | POST /api/v2/clientClasses/{collectionId}/subclasses | |
| POST /Services/REST/v1/addDHCPVendorDeploymentOption | POST /api/v2/{collection}/{collectionId}/deploymentOptions | |
| POST /Services/REST/v1/addDNSDeploymentOption | POST /api/v2/{collection}/{collectionId}/deploymentOptions | |
| POST /Services/REST/v1/addDNSDeploymentRole | POST /api/v2/deploymentRoles | |
| POST /Services/REST/v1/addDevice | POST /api/v2/configurations/{collectionId}/devices | |
| POST /Services/REST/v1/addDeviceInstance (deprecated) | POST /api/v2/zones/{collectionId}/resourceRecords <br>or<br>POST /api/v2/networks/{collectionId}/addresses | |
| POST /Services/REST/v1/addDeviceSubtype | POST /api/v2/deviceTypes/{collectionId}/deviceSubtypes | |
| POST /Services/REST/v1/addDeviceType | POST /api/v2/deviceTypes | |
| POST /Services/REST/v1/addEntity | POST /api/v2/{collection} <br>POST /api/v2/{collectionId}/{collectionId}/{subcollection} | |
| POST /Services/REST/v1/addEnumZone | POST /api/v2/views/{collectionId}/zones <br>POST /api/v2/zones/{collectionId}/zones | |
| POST /Services/REST/v1/addEnumNumber | POST /api/v2/zones/{collectionId}/zones | |
| POST /Services/REST/v1/addExternalHostRecord | POST /api/v2/zones/{collectionId}/resourceRecords | |
| POST /Services/REST/v1/addGenericRecord | POST /api/v2/zones/{collectionId}/resourceRecords | |
| POST /Services/REST/v1/addHINFORecord | POST /api/v2/zones/{collectionId}/resourceRecords | |
| POST /Services/REST/v1/addHostRecord | POST /api/v2/zones/{collectionId}/resourceRecords | |
| POST /Services/REST/v1/addIP4BlockByCIDR | POST /api/v2/configurations/{collectionId}/blocks | |
| POST /Services/REST/v1/addIP4BlockByRange | POST /api/v2/configurations/{collectionId}/blocks | |
| POST /Services/REST/v1/addIP4IPGroupByRange | POST /api/v2/networks/{collectionId}/ipGroups | |
| POST /Services/REST/v1/addIP4IPGroupBySize | POST /api/v2/networks/{collectionId}/ipGroups | "range": "\<offset>,\<size>" <br>"range": "\<offset>,\<percentage>" |
| POST /Services/REST/v1/addIP4Network | POST /api/v2/blocks/{collectionId}/networks | |
| POST /Services/REST/v1/addIP4ReconciliationPolicy | POST /api/v2/{collection}/{collectionId}/reconciliationPolicies | |
| POST /Services/REST/v1/addIP4Template | POST /api/v2/configurations/{collectionId}/templates | |
| POST /Services/REST/v1/addIP6Address | POST /api/v2/networks/{collectionId}/addresses | |
| POST /Services/REST/v1/addIP6BlockByMACAddress | POST /api/v2/blocks/{collectionId}/blocks | |
| POST /Services/REST/v1/addIP6BlockByPrefix | POST /api/v2/blocks/{collectionId}/blocks | |
| POST /Services/REST/v1/addIP6NetworkByPrefix | POST /api/v2/blocks/{collectionId}/networks | |
| POST /Services/REST/v1/addMACAddress | POST /api/v2/configurations/{collectionId}/macAddresses | |
| POST /Services/REST/v1/addMXRecord | POST /api/v2/zones/{collectionId}/resourceRecords | |
| POST /Services/REST/v1/addNAPTRRecord | POST /api/v2/zones/{collectionId}/resourceRecords | |
| POST /Services/REST/v1/addParentBlock | POST /api/v2/configurations/{collectionId}/blocks <br>POST /api/v2/blocks/{collectionId}/blocks | POST an IPv4Block or IPv6Block resource to the current parent's `/blocks` sub-collection using a range field value which spans the total range of the siblings. |
| POST /Services/REST/v1/addParentBlockWithProperties | POST /api/v2/blocks/{collectionId}/blocks | |
| POST /Services/REST/v1/addRawDeploymentOption | POST /api/v2/{collection}/{collectionId}/deploymentOptions | |
| POST /Services/REST/v1/addResourceRecord | POST /api/v2/zones/{collectionId}/resourceRecords | |
| POST /Services/REST/v1/addResponsePolicy | POST /api/v2/configurations/{collectionId}/responsePolicies | |
| POST /Services/REST/v1/addResponsePolicyItem | POST /api/v2/responsePolicies/{collectionId}/policyItems | |
| POST /Services/REST/v1/addSRVRecord | POST /api/v2/zones/{collectionId}/resourceRecords | |
| POST /Services/REST/v1/addServer | POST /api/v2/configurations/{collectionId}/servers | |
| POST /Services/REST/v1/addStartOfAuthority | POST /api/v2/{collection}/{collectionId}/deploymentOptions | |
| POST /Services/REST/v1/addTFTPDeploymentRole | POST /api/v2/tftpGroups/{collectionId}/deploymentRoles | |
| POST /Services/REST/v1/addTFTPFile | POST /api/v2/{collection}/{collectionId}/files | |
| POST /Services/REST/v1/addTFTPFolder | POST /api/v2/{collection}/{collectionId}/files | |
| POST /Services/REST/v1/addTFTPGroup | POST /api/v2/configurations/{collectionId}/tftpGroups | |
| POST /Services/REST/v1/addTXTRecord | POST /api/v2/zones/{collectionId}/resourceRecords | |
| POST /Services/REST/v1/addTag | POST /api/v2/tagGroups/{collectionId}/tags <br>POST /api/v2/tags/{collectionId}/tags | |
| POST /Services/REST/v1/addTagGroup | POST /api/v2/tagGroups | |
| POST /Services/REST/v1/addUser | POST /api/v2/users | |
| POST /Services/REST/v1/addUserDefinedField | POST /api/v2/userDefinedFieldDefinitions | |
| POST /Services/REST/v1/addUserDefinedLink | POST /api/v2/userDefinedLinkDefinitions | |
| POST /Services/REST/v1/addUserGroup | POST /api/v2/userGroups | |
| POST /Services/REST/v1/addVendorOptionDefinition | POST /api/v2/vendorProfiles/{collectionId}/deploymentOptionDefinitions | |
| POST /Services/REST/v1/addVendorProfile | POST /api/v2/vendorProfiles | |
| POST /Services/REST/v1/addView | POST /api/v2/configurations/{collectionId}/views | |
| POST /Services/REST/v1/addZone | POST /api/v2/views/{collectionId}/zones <br>POST /api/v2/zones/{collectionId}/zones | |
| POST /Services/REST/v1/addZoneTemplate | POST /api/v2/configurations/{collectionId}/templates <br>POST /api/v2/views/{collectionId}/templates | |
| POST /Services/REST/v1/applyIP4NetworkTemplate (deprecated) | POST /api/v2/templates/{collectionId}/templateApplications | |
| POST /Services/REST/v1/applyIP4Template | POST /api/v2/templates/{collectionId}/templateApplications | |
| POST /Services/REST/v1/assignIP4Address | POST /api/v2/networks/{collectionId}/addresses | |
| POST /Services/REST/v1/assignIP6Address | POST /api/v2/networks/{collectionId}/addresses | |
| POST /Services/REST/v1/assignNextAvailableIP4Address | POST /api/v2/networks/{collectionId}/addresses | |
| POST /Services/REST/v1/assignOrUpdateTemplate | PUT /api/v2/zones/{id} <br>PUT /api/v2/blocks/{id} <br>PUT /api/v2/networks/{id} <br>PUT /api/v2/ranges/{id} <br>PUT /api/v2/addresses/{id} <br>POST /api/v2/zones/{collectionId}/templateApplications <br>POST /api/v2/blocks/{collectionId}/templateApplications <br>POST /api/v2/networks/{collectionId}/templateApplications <br>POST /api/v2/ranges/{collectionId}/templateApplications <br>POST /api/v2/addresses/{collectionId}/templateApplications | To assign a template, update the template field of the resource. <br>To apply a template, send a POST request to the `/templateApplications` subcollection of the resource. |
| POST /Services/REST/v1/associateMACAddressWithPool | POST /api/v2/macPools/{collectionId}/macAddresses | |
| POST /Services/REST/v1/breakReplication | PATCH /api/v2/databases/{id} | Send request body: `{"state": "BREAK"}` |
| POST /Services/REST/v1/breakXHAPair | DELETE /api/v2/servers/{id} <br>or<br>PATCH /api/v2/servers/{id} | For PATCH, send request body: `{"state": "BREAK"}` |
| PUT /Services/REST/v1/changeStateIP4Address | PUT /api/v2/addresses/{id} | |
| DELETE /Services/REST/v1/clearIP6Address | DELETE /api/v2/addresses/{id} | |
| POST /Services/REST/v1/configureAuditLogExport | PUT /api/v2/settings/{id} | |
| POST /Services/REST/v1/configureServerServices | PUT /api/v2/servers/{collectionId}/services/{id} | |
| POST /Services/REST/v1/configureStreamingReplication | PUT /api/v2/databases/{id} | |
| POST /Services/REST/v1/createXHAPair | POST /api/v2/configurations/{collectionId}/servers | |
| GET /Services/REST/v1/customSearch | GET /api/v2?filter={filter predicate} | |
| DELETE /Services/REST/v1/delete | DELETE /api/v2/{collection}/{id} <br>DELETE /api/v2/{collection}/{collectionId}/{subcollection}/{id} | |
| DELETE /Services/REST/v1/deleteAccessRight | DELETE /api/v2/accessRights/{id} | |
| DELETE /Services/REST/v1/deleteDHCP6ClientDeploymentOption | DELETE /api/v2/deploymentOptions/{id} | |
| DELETE /Services/REST/v1/deleteDHCP6ServiceDeploymentOption | DELETE /api/v2/deploymentOptions/{id} | |
| DELETE /Services/REST/v1/deleteDHCPClientDeploymentOption | DELETE /api/v2/deploymentOptions/{id} | |
| DELETE /Services/REST/v1/deleteDHCPDeploymentRole | DELETE /api/v2/deploymentRoles/{id} | |
| DELETE /Services/REST/v1/deleteDHCPServiceDeploymentOption | DELETE /api/v2/deploymentOptions/{id} | |
| DELETE /Services/REST/v1/deleteDHCPVendorDeploymentOption | DELETE /api/v2/deploymentOptions/{id} | |
| DELETE /Services/REST/v1/deleteDNSDeploymentOption | DELETE /api/v2/deploymentOptions/{id} | |
| DELETE /Services/REST/v1/deleteDNSDeploymentRole | DELETE /api/v2/deploymentRoles/{id} | |
| DELETE /Services/REST/v1/deleteDNSDeploymentRoleForView | DELETE /api/v2/deploymentRoles/{id} | |
| DELETE /Services/REST/v1/deleteDeviceInstance (deprecated) | DELETE /api/v2/addresses/{id} <br>or<br>DELETE /api/v2/macAddresses/{id} | |
| DELETE /Services/REST/v1/deleteResponsePolicyItem | DELETE /api/v2/policyItems/{id} | |
| DELETE /Services/REST/v1/deleteUserDefinedField | DELETE /api/v2/userDefinedFieldDefinitions/{id} | |
| DELETE /Services/REST/v1/deleteUserDefinedLink | DELETE /api/v2/userDefinedLinkDefinitions/{id} | |
| DELETE /Services/REST/v1/deleteWithOptions | DELETE /api/v2/{collection}/{id} | |
| PUT /Services/REST/v1/denyMACAddress | POST /api/v2/macPools/{collectionId}/macAddresses | |
| POST /Services/REST/v1/deployServer | POST /api/v2/servers/{collectionId}/deployments | |
| POST /Services/REST/v1/deployServerConfig | POST /api/v2/servers/{collectionId}/deployments | Only one service can be deployed at a time |
| POST /Services/REST/v1/deployServerServices | POST /api/v2/servers/{collectionId}/deployments | |
| PUT /Services/REST/v1/editXHAPair | PUT /api/v2/servers/{id} | |
| POST /Services/REST/v1/establishTrustRelationship | POST /api/v2/trustRelationships | |
| POST /Services/REST/v1/failoverReplication | PATCH /api/v2/databases/{collectionId)/servers/{id} | Send request body `{"state": "PRIMARY"}` |
| PUT /Services/REST/v1/failoverXHA | PATCH /api/v2/servers/{id} | Send request body: `{"state": "FAILOVER"}` |
| GET /Services/REST/v1/findResponsePoliciesWithItem | GET /policyItems?filter=name:'{fqdn}'&fields=_links.collection | |

### G-L API endpoints

| RESTv1 API | RESTv2 Endpoint | Notes |
|-------------|----------------|-------|
| GET /Services/REST/v1/getAccessRight | GET /api/v2/accessRights/{id} | |
| GET /Services/REST/v1/getAccessRightsForEntity | GET /api/v2/{collection}/{collectionId}/accessRights | |
| GET /Services/REST/v1/getAccessRightsForUser | GET /api/v2/users/{collectionId}/accessRights | |
| GET /Services/REST/v1/getAliasesByHint | GET /api/v2/zones/{collectionId}/resourceRecords?filter=type:'AliasRecord' | |
| GET /Services/REST/v1/getAllUsedLocations | GET example to be provided for 9.6 | |
| GET /Services/REST/v1/getAuditLogExportStatus | GET /api/v2/settings?filter=type:'AuditDataSettings' | |
| GET /Services/REST/v1/getConfigurationGroups | GET /api/v2/configurations?fields=configurationGroup | |
| GET /Services/REST/v1/getConfigurationSetting | GET /api/v2/configurations/{id} | |
| GET /Services/REST/v1/getConfigurationsByGroup | GET /api/v2/configurations?filter=configurationGroup:'{name}' | |
| GET /Services/REST/v1/getDHCP6ClientDeploymentOption | GET /api/v2/deploymentOptions/{id} | |
| GET /Services/REST/v1/getDHCP6ServiceDeploymentOption | GET /api/v2/deploymentOptions/{id} | |
| GET /Services/REST/v1/getDHCPClientDeploymentOption | GET /api/v2/deploymentOptions/{id} | |
| GET /Services/REST/v1/getDHCPDeploymentRole | GET /api/v2/deploymentRoles/{id} | |
| GET /Services/REST/v1/getDHCPServiceDeploymentOption | GET /api/v2/deploymentOptions/{id} | |
| GET /Services/REST/v1/getDHCPVendorDeploymentOption | GET /api/v2/deploymentOptions/{id} | |
| GET /Services/REST/v1/getDNSDeploymentOption | GET /api/v2/deploymentOptions/{id} | |
| GET /Services/REST/v1/getDNSDeploymentRole | GET /api/v2/deploymentRoles/{id} | |
| GET /Services/REST/v1/getDNSDeploymentRoleForView | GET /api/v2/deploymentRoles?filter=serverInterface.id:{interfaceId} and view.id:{viewId} | |
| GET /Services/REST/v1/getDependentRecords | GET /api/v2/resourceRecords/{collectionId}/dependentRecords <br>GET /api/v2/addresses/{collectionId}/dependentRecords | |
| GET /Services/REST/v1/getDeploymentOptions | GET /api/v2/deploymentOptions | |
| GET /Services/REST/v1/getDeploymentRoles | GET /api/v2/deploymentRoles | |
| GET /Services/REST/v1/getDeploymentTaskStatus | GET /api/v2/deployments/{id} | |
| GET /Services/REST/v1/getDiscoveredDevice | GET /api/v2/reconciliationPolicies/{collectionId}/discoveredDevices/{id} | |
| GET /Services/REST/v1/getDiscoveredDeviceArpEntries | GET /api/v2/reconciliationPolicies/{collectionId}/discoveredDevices?filter=type:'DiscoveredARPEntry' and device.id:{deviceId} | |
| GET /Services/REST/v1/getDiscoveredDeviceHosts | GET /api/v2/reconciliationPolicies/{collectionId}/discoveredDevices?filter=type:'DiscoveredHost' and device.id:{deviceId} | |
| GET /Services/REST/v1/getDiscoveredDeviceInterfaces | GET /api/v2/reconciliationPolicies/{collectionId}/discoveredDevices?filter=type:'DiscoveredInterface' and device.id:{deviceId} | |
| GET /Services/REST/v1/getDiscoveredDeviceMacAddressEntries | GET /api/v2/reconciliationPolicies/{collectionId}/discoveredDevices?filter=type:'DiscoveredMACAddress' and device.id:{deviceId} | |
| GET /Services/REST/v1/getDiscoveredDeviceNetworks | GET /api/v2/reconciliationPolicies/{collectionId}/discoveredDevices?filter=type:'DiscoveredNetwork' and device.id:{deviceId} | |
| GET /Services/REST/v1/getDiscoveredDeviceVlans | GET /api/v2/reconciliationPolicies/{collectionId}/discoveredDevices?filter=type:'DiscoveredVLAN' and device.id:{deviceId} | |
| GET /Services/REST/v1/getDiscoveredDevices | GET /api/v2/reconciliationPolicies/{collectionId}/discoveredDevices?filter=type:in('DiscoveredRouter', 'DiscoveredSwitch') | |
| GET /Services/REST/v1/getEntities | GET /api/v2/{collection} <br>GET /api/v2/{collection}/{collectionId}/{subcollection} | |
| GET /Services/REST/v1/getEntitiesByName | GET /api/v2?filter=name:'{name}' | |
| GET /Services/REST/v1/getEntitiesByNameUsingOptions | GET /api/v2?filter=name:'{name}' | |
| GET /Services/REST/v1/getEntityByCIDR | For IPv4 blocks with a configuration parent: <br>GET /api/v2/blocks?filter=configuration.id:{id} and range:'{range}' <br>For IPv4 sub blocks with an IPv4 block parent: <br>GET /api/v2/blocks/{collectionId}/blocks?filter=range:'{range}' <br>For IPv4 networks: <br>GET /api/v2/blocks/{collectionId}/networks?filter=range:'{range}' | |
| GET /Services/REST/v1/getEntityById | GET /api/v2?filter=id:{id} | |
| GET /Services/REST/v1/getEntityByName | GET /api/v2?filter=name:'{name}' | |
| GET /Services/REST/v1/getEntityByPrefix | For IPv6 blocks with a configuration parent: <br>GET /api/v2/blocks?filter=configuration.id:{id} and range:startsWith({prefix}) <br>For IPv6 sub blocks with an IPv6 block parent: <br>GET /api/v2/blocks/{collectionId}/blocks?filter=range:startsWith({prefix}) <br>For IPv6 networks: <br>GET /api/v2/blocks/{collectionId}/networks?filter=range:startsWith({prefix}) | |
| GET /Services/REST/v1/getEntityByRange | GET /api/v2/networks/{collectionId}/ranges?filter=range:'{range}' | |
| GET /Services/REST/v1/getHostRecordsByHint | GET /api/v2/zones/{collectionId}/resourceRecords?filter={filter predicate} | |
| GET /Services/REST/v1/getIP4Address | GET /api/v2/addresses?filter=address:'{address}' <br>GET /api/v2/networks/{collectionId}/addresses?filter=address:'{address}' | |
| GET /Services/REST/v1/getIP4NetworksByHint | GET /api/v2/networks?filter=range:startsWith('{prefix}') | |
| GET /Services/REST/v1/getIP6Address | GET /api/v2/addresses?filter=address:'{address}' <br>GET /api/v2/networks/{collectionId}/addresses?filter=address:'{address}' | |
| GET /Services/REST/v1/getIPRangedByIP | GET /api/v2/ranges?filter=range:contains('{address}') | |
| GET /Services/REST/v1/getKSK | GET /api/v2/signingKeys/{id} | This does not support the formats supported by /v1/getKSK yet, it will only respond with a JSON representation of the resource. |
| GET /Services/REST/v1/getLatestMigrationLog | GET /api/v2/imports?orderBy=desc(id)&fields=embed(logs) | |
| GET /Services/REST/v1/getLinkedEntities | GET /api/v2/tags/{collectionId}/taggedResources <br>GET /api/v2/userGroups/{collectionId}/users <br>GET /api/v2/addresses/{collectionId}/resourceRecords <br>GET /api/v2/resourceRecords/{collectionId}/dependentRecords <br>GET /api/v2/macPools/{collectionId}/macAddresses <br>GET /api/v2/serverGroups/{collectionId}/servers <br>GET /api/v2/locations/{collectionId}/annotatedResources | |
| GET /Services/REST/v1/getLinkedEntitiesByUDL | GET /api/v2/userDefinedLinkDefinitions/{collectionId}/linkedResources | |
| GET /Services/REST/v1/getLinkedEntitiesEx | See GET /Services/REST/v1/getLinkedEntities | |
| GET /Services/REST/v1/getLinkedIP4ObjectConflicts | GET /api/v2/templates/{id}/conflictingResources | |
| GET /Services/REST/v1/getLocationByCode | GET /api/v2/locations?filter=code:'{code}' | |
| GET /Services/REST/v1/getMACAddress | GET /api/v2/macAddresses/{id} | |
| GET /Services/REST/v1/getMACAddressesInPool | GET /api/v2/macPools/{collectionId}/macAddresses | |
| GET /Services/REST/v1/getMaxAllowedRange | GET example to be provided for 9.5 | |
| GET /Services/REST/v1/getNetworkLinkedProperties | GET /api/v2/networks/{id}/addresses?fields=embed(dependentRecords) | |
| GET /Services/REST/v1/getNextAvailableIP4Address | GET /api/v2/networks/{collectionId}/addresses?filter=state:'UNASSIGNED' | |
| GET /Services/REST/v1/getNextAvailableIP4Network | POST /api/v2/blocks/{collectionId}/networks | Set the `range` field to the value /<prefix> where \<prefix>is the size of network desired. |
| GET /Services/REST/v1/getNextAvailableIP6Address | GET /api/v2/networks/{collectionId}/address?filter=state:'UNASSIGNED' | |
| GET /Services/REST/v1/getNextAvailableIPRange | POST /api/v2/configurations/{collectionId}/blocks <br>POST /api/v2/blocks/{collectionId}/blocks <br>POST /api/v2/blocks/{collectionId}/networks | Set the `range` field to the value /<prefix> where \<prefix>is the size of network desired. |
| GET /Services/REST/v1/getNextIP4Address | GET /api/v2/networks/{collectionId}/addresses?filter=state:'UNASSIGNED' | |
| GET /Services/REST/v1/getParent | Will not implement | The URI of a resource's collection can be found in its `_links.collection.href` field. To receive resource representations with a `_links` field, the request must set its `Accept` header to `*/*` or `application/hal+json`. |
| GET /Services/REST/v1/getProbeData | To be implemented in 10.0 | |
| GET /Services/REST/v1/getProbeStatus | To be implemented in 10.0 | |
| GET /Services/REST/v1/getReplicationInfo | GET /api/v2/databases/{id}?fields=embed(servers) | |
| GET /Services/REST/v1/getServerDeploymentRoles | GET /api/v2/servers/{collectionId}/deploymentRoles | |
| GET /Services/REST/v1/getServerForRole | GET /api/v2/deploymentRoles/{collectionId}/interfaces | The NetworkInterface and PublishedInterface resources have a `server` field. |
| GET /Services/REST/v1/getServerServices | GET /api/v2/servers/{collectionId}/services | Service resources returned will depend on supported services for the DNS/DHCP Server version. The LicenseServer resource is only returned for DNS/DHCP Server version 9.5 and greater. |
| GET /Services/REST/v1/getServerServicesConfigurationStatus | GET /api/v2/servers/{collectionId}/services/{id} | |
| GET /Services/REST/v1/getSharedNetworks | GET /api/v2/tags/{collectionId}/taggedResources | |
| GET /Services/REST/v1/getSystemInfo | GET /api/v2/settings?filter=type:'SystemSettings' | |
| GET /Services/REST/v1/getTemplateTaskStatus | GET /api/v2/templateApplications/{id} | |
| GET /Services/REST/v1/getUserDefinedFields | GET /api/v2/userDefinedFieldDefinitions | |
| GET /Services/REST/v1/getUserDefinedLink | GET /api/v2/userDefinedLinkDefinitions | |
| GET /Services/REST/v1/getZonesByHint | GET /api/v2/zones?filter={filter predicate} | |
| GET /Services/REST/v1/isAddressAllocated | GET /api/v2/macAddresses/{collectionId}/addresses | The `/addresses` subcollection of MACAddress resources contains all IP addresses currently assigned to the MAC address. |
| GET /Services/REST/v1/isMigrationRunning | GET /api/v2/imports/{id} | Check state field for the value `RUNNING` |
| GET /Services/REST/v1/login | POST /api/v2/sessions | |
| GET /Services/REST/v1/loginWithOptions | POST /api/v2/sessions | |
| GET /Services/REST/v1/logout | PATCH /api/v2/sessions/current | Send request body: `{"state": "LOGGED_OUT"}` |

### M-R API endpoints

| RESTv1 API | RESTv2 Endpoint | Notes |
|-------------|----------------|-------|
| POST /Services/REST/v1/mergeBlocksWithParent | POST /api/v2/{collection}/{collectionId}/merges | |
| POST /Services/REST/v1/mergeSelectedBlocksOrNetworks | POST /api/v2/{collection}/{collectionId}/merges | |
| POST /Services/REST/v1/migrateFile | PATCH /api/v2/imports/{id} | Send request body: `{"state": "QUEUED"}` |
| PUT /Services/REST/v1/moveDeploymentRoles | POST /api/v2/servers/{collectionId}/moves | |
| PUT /Services/REST/v1/moveIPObject | POST /api/v2/blocks/{collectionId}/moves <br>POST /api/v2/networks/{collectionId}/moves <br>POST /api/v2/addresses/{collectionId}/moves | |
| PUT /Services/REST/v1/moveResourceRecord | POST /api/v2/resourceRecords/{collectionId}/moves | |
| POST /Services/REST/v1/quickDeploy | POST /api/v2/zones/{collectionId}/deployments <br>POST /api/v2/networks/{collectionId}/deployments | |
| POST /Services/REST/v1/reapplyTemplate | POST /api/v2/zones/{collectionId}/templateApplications <br>POST /api/v2/blocks/{collectionId}/templateApplications <br>POST /api/v2/networks/{collectionId}/templateApplications <br>POST /api/v2/ranges/{collectionId}/templateApplications <br>POST /api/v2/addresses/{collectionId}/templateApplications | |
| POST /Services/REST/v1/reassignIP6Address | PUT /api/v2/addresses/{id} | |
| POST /Services/REST/v1/removeTrustRelationship | DELETE /api/v2/trustRelationships/{id} | |
| PUT /Services/REST/v1/replaceServer | PUT /api/v2/servers/{id} | The server must first be disabled using a PATCH request with `{"state": "DISABLED"}` |
| PUT /Services/REST/v1/resizeRange | PUT /api/v2/blocks/{id} <br>PUT /api/v2/networks/{id} <br>PUT /api/v2/ranges/{id} | Set `range` field to the new range. |
| POST /Services/REST/v1/rolloverTSIGKey | POST /api/v2/signingKeys/{id} | Set `privateKey` to `null` |
| GET /Services/REST/v1/searchByCategory | Will not implement | Object categories are not well defined. Use the `filter` query parameter as a replacement. |

### S-Z API endpoints

| RESTv1 API | RESTv2 Endpoints | Notes |
|-------------|------------------|-------|
| GET /Services/REST/v1/searchByObjectTypes | GET /api/v2?filter=type:'{type}' | |
| POST /Services/REST/v1/selectiveDeploy | POST /api/v2/deployments | |
| PUT /Services/REST/v1/shareNetwork | PUT /api/v2/networks/{id} | Set the `sharedNetworkTag` field to the resource of the shared network tag. |
| POST /Services/REST/v1/splitIP4Network | POST /api/v2/blocks/{collectionId}/splits | |
| PUT /Services/REST/v1/startProbe | To be implemented in 10.0 | |
| POST /Services/REST/v1/terminateUserSessions | PATCH /api/v2/sessions/{id} | Send request body: `{"state": "TERMINATED"}` |
| POST /Services/REST/v1/unassignIP4NetworkTemplate | PUT /api/v2/zones/{id} <br>PUT /api/v2/blocks/{id} <br>PUT /api/v2/networks/{id} <br>PUT /api/v2/ranges/{id} <br>PUT /api/v2/addresses/{id} | Update the `template` field of a resource to null to unassign a template. |
| POST /Services/REST/v1/unassignIP4Template | PUT /api/v2/zones/{id} <br>PUT /api/v2/blocks/{id} <br>PUT /api/v2/networks/{id} <br>PUT /api/v2/ranges/{id} <br>PUT /api/v2/addresses/{id} | Update the `template` field of a resource to null to unassign a template. |
| PUT /Services/REST/v1/unlinkEntities | DELETE /api/v2/{collection}/{collectionId}/tags/{id} <br>DELETE /api/v2/userGroups/{collectionId}/users/{id} <br>DELETE /api/v2/macPools/{collectionId}/macAddresses/{id} <br>DELETE /api/v2/serverGroups/{collectionId}/servers/{id} <br>DELETE /api/v2/signingPolicies/{collectionId}/appliedResources/{id} | |
| PUT /Services/REST/v1/unlinkEntitiesEx | See PUT /Services/REST/v1/unlinkEntities | |
| PUT /Services/REST/v1/unshareNetwork | PUT /api/v2/networks/{id} | Set `sharedNetworkTag` to null. |
| PUT /Services/REST/v1/update | PUT /api/v2/{collection}/{id} | |
| PUT /Services/REST/v1/updateAccessRight | PUT /api/v2/accessRights/{id} | |
| POST /Services/REST/v1/updateBulkUdf | To be implemented (TBD) | |
| PUT /Services/REST/v1/updateConfigurationSetting | PUT /api/v2/configurations/{id} | |
| PUT /Services/REST/v1/updateDHCP6ClientDeploymentOption | PUT /api/v2/deploymentRoles/{id} | |
| PUT /Services/REST/v1/updateDHCP6ServiceDeploymentOption | PUT /api/v2/deploymentRoles/{id} | |
| PUT /Services/REST/v1/updateDHCPClientDeploymentOption | PUT /api/v2/deploymentRoles/{id} | |
| PUT /Services/REST/v1/updateDHCPDeploymentRole | PUT /api/v2/deploymentRoles/{id} | |
| PUT /Services/REST/v1/updateDHCPServiceDeploymentOption | PUT /api/v2/deploymentOptions/{id} | |
| PUT /Services/REST/v1/updateDHCPVendorDeploymentOption | PUT /api/v2/deploymentOptions/{id} | |
| PUT /Services/REST/v1/updateDNSDeploymentOption | PUT /api/v2/deploymentOptions/{id} | |
| PUT /Services/REST/v1/updateDNSDeploymentRole | PUT /api/v2/deploymentRoles/{id} | |
| PUT /Services/REST/v1/updateRawDeploymentOption | PUT /api/v2/deploymentOptions/{id} | |
| PUT /Services/REST/v1/updateRetentionSettings | PUT /api/v2/settings/{id} | |
| PUT /Services/REST/v1/updateUserDefinedField | PUT /api/v2/userDefinedFieldDefinitions/{id} | |
| PUT /Services/REST/v1/updateUserDefinedLink | PUT /api/v2/userDefinedLinkDefinitinons/{id} | |
| PUT /Services/REST/v1/updateUserPassword | PATCH /api/v2/users/{id} | Send request body: `{"password": "XXXXXXXX"}` |
| PUT /Services/REST/v1/updateWithOptions | Option LinkToExternalHost | Set `x-bcn-link-to-external-host` HTTP header with PUT request |
| | Option disable: PATCH /api/v2/servers/{id} | Send a PATCH request with `{"state": "DISABLE"}` |
| | Option resetControl: PATCH /api/v2/servers/{id} | Send a PATCH request with `{"state": "RESET_CONTROL"}` |
| POST /Services/REST/v1/uploadDockerImage | To be implemented for 9.6 | |
| POST /Services/REST/v1/uploadMigrationFile | POST /api/v2/imports | |
| POST /Services/REST/v1/uploadResponsePolicyFile | POST /api/v2/responsePolicies/{collectionId}/imports | |
| POST /Services/REST/v1/uploadResponsePolicyItems (deprecated) | POST /api/v2/responsePolicies/{collectionId}/imports | |

## Terms and Conditions

**READ THIS BEFORE INSTALLING OR USING BLUECAT PRODUCTS, SERVICES, AND DOCUMENTATION** 

The material herein is subject to the applicable BlueCat License Agreement previously entered into between BlueCat and your company, or if none, then to BlueCat's standard terms and conditions which you can view and download from https://www.bluecatnetworks.com/services-support/support/license-agreements/. BlueCat reserves the right to revise this material at any time without notice. Company names and data used in screens and sample output are fictitious, unless otherwise stated.

### Copyright

©2001—2024 BlueCat Networks (USA) Inc. and its affiliates (collectively 'BlueCat'). All rights reserved. This document contains BlueCat confidential and proprietary information and is intended only for the person(s) to whom it is transmitted. Any reproduction of this document, in whole or in part, without the prior written consent of BlueCat is prohibited.

### Trademarks

Proteus, Adonis, BlueCat DNS/DHCP Server, BlueCat Address Manager, BlueCat DNS Edge, BlueCat Device Registration Portal, BlueCat DNS Integrity, BlueCat Gateway, BlueCat Mobile Security, BlueCat Address Manager for Windows Server, and BlueCat Threat Protection are trademarks of BlueCat.

iDRAC is a registered trademark of Dell Inc. Windows is a registered trademark of Microsoft Corporation. UNIX is a registered trademark of The Open Group. Linux is a registered trademark of Linus Torvalds. QRadar is a registered trademark of IBM. ArcSight is a registered trademark of Hewlett Packard. Ubuntu is a registered trademark of Canonical Ltd. CentOS is a trademark of the CentOS Project. Cisco Umbrella is a trademark of Cisco. Amazon Web Services ("AWS") and the Amazon Web Services logo are registered trademarks of Amazon Web Services, Inc. or its affiliates. Microsoft Azure and the Azure logo are registered trademarks of Microsoft Corporation. Google Cloud Platform services is a trademark of Google LLC. All other product and company names are registered trademarks or trademarks of their respective holders.