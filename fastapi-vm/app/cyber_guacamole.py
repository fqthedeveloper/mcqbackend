import requests
import urllib3

urllib3.disable_warnings()

GUACAMOLE_URL = "http://127.0.0.1:8080/guacamole"

GUAC_USERNAME = "guacadmin"

GUAC_PASSWORD = "guacadmin"

DATASOURCE = "mysql"


# =========================================================
# LOGIN
# =========================================================

def get_guacamole_token():

    response = requests.post(

        f"{GUACAMOLE_URL}/api/tokens",

        data={

            "username":
                GUAC_USERNAME,

            "password":
                GUAC_PASSWORD,
        },

        verify=False
    )

    response.raise_for_status()

    return response.json()["authToken"]


# =========================================================
# CREATE CONNECTION
# =========================================================

def create_guacamole_connection(

    vm_name,

    vm_ip,

    username,

    password,

    os_type="linux"
):

    token = get_guacamole_token()

    protocol = "rdp"

    port = "3389"

    if os_type == "linux":

        protocol = "ssh"

        port = "22"

    payload = {

        "parentIdentifier":
            "ROOT",

        "name":
            vm_name,

        "protocol":
            protocol,

        "parameters": {

            "hostname":
                vm_ip,

            "port":
                port,

            "username":
                username,

            "password":
                password,

            "ignore-cert":
                "true",

            "security":
                "any",
        },

        "attributes": {}
    }

    response = requests.post(

        f"{GUACAMOLE_URL}/api/session/data/{DATASOURCE}/connections?token={token}",

        json=payload,

        verify=False
    )

    response.raise_for_status()

    data = response.json()

    connection_id = data["identifier"]

    return {

        "connection_id":
            connection_id,

        "url":
            f"/guacamole/#/client/{connection_id}"
    }


# =========================================================
# DELETE CONNECTION
# =========================================================

def delete_guacamole_connection(
    connection_id
):

    token = get_guacamole_token()

    requests.delete(

        f"{GUACAMOLE_URL}/api/session/data/{DATASOURCE}/connections/{connection_id}?token={token}",

        verify=False
    )


# =========================================================
# TEST CONNECTION
# =========================================================

def test_guacamole():

    token = get_guacamole_token()

    response = requests.get(

        f"{GUACAMOLE_URL}/api/session/data/{DATASOURCE}/connections?token={token}",

        verify=False
    )

    response.raise_for_status()

    return response.json()