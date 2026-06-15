import random
import string


def random_ip():
    return f'10.10.{random.randint(1, 200)}.{random.randint(2, 254)}'


def random_username():
    return 'user' + ''.join(random.choices(string.ascii_lowercase, k=4))


def random_service_port():
    return random.randint(2000, 9999)


def generate_variables(schema: dict):

    generated = {}

    for key, value in schema.items():

        if value == 'random_ip':
            generated[key] = random_ip()

        elif value == 'random_username':
            generated[key] = random_username()

        elif value == 'random_port':
            generated[key] = random_service_port()

        else:
            generated[key] = value

    return generated