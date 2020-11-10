import demistomock as demisto  # noqa: F401
from CommonServerPython import *  # noqa: F401
# noqa: F401
# noqa: F401
# noqa: F401
# noqa: F401


import traceback

# Disable insecure warnings
requests.packages.urllib3.disable_warnings()

'''CLIENT CLASS'''


class Client(BaseClient):
    """
    ServiceNow IAM Client class that implements logic to authenticate with ServiceNow.
    """

    def test(self):
        uri = '/table/sys_user?sysparm_limit=1'
        self._http_request(method='GET', url_suffix=uri)

    def get_user(self, email):
        uri = 'table/sys_user'
        query_params = {
            'email': email
        }

        res = self._http_request(
            method='GET',
            url_suffix=uri,
            params=query_params
        )

        if res and len(res.get('result', [])) == 1:
            return res.get('result')[0]
        return None

    def create_user(self, user_data):
        uri = 'table/sys_user'
        res = self._http_request(
            method='POST',
            url_suffix=uri,
            data=json.dumps(user_data)
        )
        return res.get('result')

    def update_user(self, user_id, user_data):
        uri = f'/table/sys_user/{user_id}'
        res = self._http_request(
            method='PATCH',
            url_suffix=uri,
            data=json.dumps(user_data)
        )
        return res.get('result')

    def get_service_now_fields(self):
        service_now_fields = {}
        uri = 'table/sys_dictionary?sysparm_query=name=sys_user'
        res = self._http_request(
            method='GET',
            url_suffix=uri
        )

        elements = res.get('result', [])
        for elem in elements:
            if elem.get('element'):
                field_name = elem.get('element')
                description = elem.get('sys_name')
                service_now_fields[field_name] = description

        return service_now_fields


'''HELPER FUNCTIONS'''


def merge(user_profile, full_user_data):
    """ Merges the user_profile and the full user data, such that existing attributes in user_profile will remain as
    they are, but attributes not provided will be added to it.

    Args:
        user_profile (dict): The user profile data, in ServiceNow format.
        full_user_data (dict): The full user data retrieved from ServiceNow.

    Return:
        (dict) The full user profile.
    """
    for attribute, value in full_user_data.items():
        if attribute not in user_profile.keys():
            user_profile[attribute] = value

    return user_profile


def handle_exception(user_profile, e, action):
    """ Handles failed responses from ServiceNow API by setting the User Profile object with the results.

    Args:
        user_profile (IAMUserProfile): The User Profile object.
        e (DemistoException): The exception error that holds the response json.
        action (IAMActions): An enum represents the current action (get, update, create, etc).
    """
    error_message = get_error_details(e.res)

    user_profile.set_result(action=action,
                            success=False,
                            error_code='',  # todo: fix in CSP if needed
                            error_message=error_message,
                            details=e.res)


def get_error_details(res):
    """ Parses the error details retrieved from ServiceNow and outputs the resulted string.

    Args:
        res (dict): The data retrieved from ServiceNow.

    Returns:
        (str) The parsed error details.
    """
    message = res.get('error', {}).get('message')
    details = res.get('error', {}).get('detail')
    return f'{message}: {details}'


'''COMMAND FUNCTIONS'''


def test_module(client):
    client.test()
    return_results('ok')


def get_mapping_fields_command(client):
    service_now_fields = client.get_service_now_fields()
    incident_type_scheme = SchemeTypeMapping(type_name=IAMUserProfile.INDICATOR_TYPE)

    for field, description in service_now_fields.items():
        incident_type_scheme.add_field(field, description)

    return GetMappingFieldsResponse([incident_type_scheme])


def get_user_command(client, args, mapper_in):
    user_profile = IAMUserProfile(user_profile=args.get('user-profile'))
    try:
        service_now_user = client.get_user(user_profile.get_attribute('email'))
        if not service_now_user:
            error_code, error_message = IAMErrors.USER_DOES_NOT_EXIST
            user_profile.set_result(action=IAMActions.GET_USER,
                                    success=False,
                                    error_code=error_code,
                                    error_message=error_message)
        else:
            user_profile.update_with_app_data(service_now_user, mapper_in)
            user_profile.set_result(
                action=IAMActions.GET_USER,
                success=True,
                active=True if service_now_user.get('active') == 'true' else False,
                iden=service_now_user.get('sys_id'),
                email=service_now_user.get('email'),
                username=service_now_user.get('user_name'),
                details=service_now_user
            )

    except DemistoException as e:
        handle_exception(user_profile, e, IAMActions.GET_USER)

    return user_profile


def enable_user_command(client, args, mapper_out, is_command_enabled, is_create_user_enabled, create_if_not_exists):
    user_profile = IAMUserProfile(user_profile=args.get('user-profile'))
    if not is_command_enabled:
        user_profile.set_result(action=IAMActions.ENABLE_USER,
                                skip=True,
                                skip_reason='Command is disabled.')
    else:
        try:
            service_now_user = client.get_user(user_profile.get_attribute('email'))
            if not service_now_user:
                if create_if_not_exists:
                    user_profile = create_user_command(client, args, mapper_out, is_create_user_enabled)
                else:
                    _, error_message = IAMErrors.USER_DOES_NOT_EXIST
                    user_profile.set_result(action=IAMActions.ENABLE_USER,
                                            skip=True,
                                            skip_reason=error_message)
            else:
                user_id = service_now_user.get('sys_id')
                user_data = {'active': True, 'locked_out': False}
                updated_user = client.update_user(user_id, user_data)
                user_profile.set_result(
                    action=IAMActions.ENABLE_USER,
                    success=True,
                    active=True,
                    iden=updated_user.get('sys_id'),
                    email=updated_user.get('email'),
                    username=updated_user.get('user_name'),
                    details=updated_user
                )

        except DemistoException as e:
            handle_exception(user_profile, e, IAMActions.ENABLE_USER)

    return user_profile


def disable_user_command(client, args, is_command_enabled):
    user_profile = IAMUserProfile(user_profile=args.get('user-profile'))
    if not is_command_enabled:
        user_profile.set_result(action=IAMActions.DISABLE_USER,
                                skip=True,
                                skip_reason='Command is disabled.')
    else:
        try:
            service_now_user = client.get_user(user_profile.get_attribute('email'))
            if not service_now_user:
                _, error_message = IAMErrors.USER_DOES_NOT_EXIST
                user_profile.set_result(action=IAMActions.DISABLE_USER,
                                        skip=True,
                                        skip_reason=error_message)
            else:
                user_id = service_now_user.get('sys_id')
                user_data = {'active': False}
                updated_user = client.update_user(user_id, user_data)
                user_profile.set_result(
                    action=IAMActions.DISABLE_USER,
                    success=True,
                    active=False,
                    iden=updated_user.get('sys_id'),
                    email=updated_user.get('email'),
                    username=updated_user.get('user_name'),
                    details=updated_user
                )

        except DemistoException as e:
            handle_exception(user_profile, e, IAMActions.DISABLE_USER)

    return user_profile


def create_user_command(client, args, mapper_out, is_command_enabled):
    user_profile = IAMUserProfile(user_profile=args.get('user-profile'))
    if not is_command_enabled:
        user_profile.set_result(action=IAMActions.CREATE_USER,
                                skip=True,
                                skip_reason='Command is disabled.')
    else:
        try:
            service_now_user = client.get_user(user_profile.get_attribute('email'))
            if service_now_user:
                _, error_message = IAMErrors.USER_ALREADY_EXISTS
                user_profile.set_result(action=IAMActions.CREATE_USER,
                                        skip=True,
                                        skip_reason=error_message)
            else:
                service_now_profile = user_profile.map_object(mapper_out)
                created_user = client.create_user(service_now_profile)
                user_profile.set_result(
                    action=IAMActions.CREATE_USER,
                    success=True,
                    active=True if created_user.get('active') == 'true' else False,
                    iden=created_user.get('sys_id'),
                    email=created_user.get('email'),
                    username=created_user.get('user_name'),
                    details=created_user
                )

        except DemistoException as e:
            handle_exception(user_profile, e, IAMActions.CREATE_USER)

    return user_profile


def update_user_command(client, args, mapper_out, is_command_enabled, is_create_user_enabled, create_if_not_exists):
    user_profile = IAMUserProfile(user_profile=args.get('user-profile'))
    if not is_command_enabled:
        user_profile.set_result(action=IAMActions.UPDATE_USER,
                                skip=True,
                                skip_reason='Command is disabled.')
    else:
        try:
            service_now_user = client.get_user(user_profile.get_attribute('email'))
            if service_now_user:
                user_id = service_now_user.get('sys_id')
                service_now_profile = user_profile.map_object(mapper_out)
                full_service_now_profile = merge(service_now_profile, service_now_user)
                updated_user = client.update_user(user_id, full_service_now_profile)
                user_profile.set_result(
                    action=IAMActions.UPDATE_USER,
                    success=True,
                    active=True if updated_user.get('active') == 'true' else False,
                    iden=updated_user.get('sys_id'),
                    email=updated_user.get('email'),
                    username=updated_user.get('user_name'),
                    details=updated_user
                )
            else:
                if create_if_not_exists:
                    user_profile = create_user_command(client, args, mapper_out, is_create_user_enabled)
                else:
                    _, error_message = IAMErrors.USER_DOES_NOT_EXIST
                    user_profile.set_result(action=IAMActions.UPDATE_USER,
                                            skip=True,
                                            skip_reason=error_message)

        except DemistoException as e:
            handle_exception(user_profile, e, IAMActions.UPDATE_USER)

    return user_profile


def main():
    user_profile = None
    params = demisto.params()
    api_version = params.get('api_version', '')
    base_url = urljoin(params['url'].strip('/'), '/api/now/')
    if api_version:
        base_url += api_version
    username = params.get('credentials', {}).get('identifier')
    password = params.get('credentials', {}).get('password')
    mapper_in = params.get('mapper-in')
    mapper_out = params.get('mapper-out')
    verify_certificate = not params.get('insecure', False)
    proxy = params.get('proxy', False)
    command = demisto.command()
    args = demisto.args()

    is_create_enabled = params.get("create-user-enabled")
    is_enable_disable_enabled = params.get("enable-disable-user-enabled")
    is_update_enabled = demisto.params().get("update-user-enabled")
    create_if_not_exists = demisto.params().get("create-if-not-exists")

    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }

    client = Client(
        base_url=base_url,
        verify=verify_certificate,
        proxy=proxy,
        headers=headers,
        ok_codes=(200, 201),
        auth=(username, password)
    )

    demisto.debug(f'Command being called is {command}')

    try:
        if command == 'iam-get-user':
            user_profile = get_user_command(client, args, mapper_in)

        elif command == 'iam-create-user':
            user_profile = create_user_command(client, args, mapper_out, is_create_enabled)

        elif command == 'iam-update-user':
            user_profile = update_user_command(client, args, mapper_out, is_update_enabled,
                                               is_create_enabled, create_if_not_exists)

        elif command == 'iam-disable-user':
            user_profile = disable_user_command(client, args, is_enable_disable_enabled)

        elif command == 'iam-enable-user':
            user_profile = enable_user_command(client, args, mapper_out, is_enable_disable_enabled,
                                               is_create_enabled, create_if_not_exists)

        if user_profile:
            return_results(user_profile)

    except Exception:
        # We don't want to return an error entry CRUD commands execution
        return_results(f'Failed to execute {command} command. Traceback: {traceback.format_exc()}')

    try:
        if command == 'test-module':
            test_module(client)

        elif command == 'get-mapping-fields':
            return_results(get_mapping_fields_command(client))

    except Exception:
        # For any other integration command exception, return an error
        return_error(f'Failed to execute {command} command. Traceback: {traceback.format_exc()}')


if __name__ in ('__main__', '__builtin__', 'builtins'):
    main()