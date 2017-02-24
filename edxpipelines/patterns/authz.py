"""
GoCD Authorization primitives.
"""

from xml.etree import ElementTree as ET

from enum import Enum

from gomatic.xml_operations import Ensurance


class Permission(Enum):
    """An enumeration of valid GoCD authorizations"""
    ADMINS = "admins"
    OPERATE = "operate"
    VIEW = "view"


def ensure_role(configurator, role):
    """
    Ensure that the supplied ``role`` is available in GoCD.

    Arguments:
        configurator (gomatic.GoCDConfigurator): the configurator to change
        role (str): The role to add
    """
    # pylint: disable=protected-access
    security_element = Ensurance(configurator._GoCdConfigurator__xml_root).ensure_child('security').element
    roles_element = Ensurance(security_element).ensure_child('roles').element
    Ensurance(roles_element).ensure_child_with_attribute('role', 'name', role)


def ensure_permissions(configurator, pipeline_group, permission, roles):
    """
    Ensure that only the ``roles`` are given the ``permission``
    in the ``pipeline_group``.

    Arguments:
        pipeline_group (gomatic.PipelineGroup)
        permission (Permission)
        roles (list): List of role names to ensure
    """
    for role in roles:
        ensure_role(configurator, role)

    authorization_element = Ensurance(pipeline_group.element).ensure_child('authorization').element
    permission_element = Ensurance(authorization_element).ensure_child(permission.value).element
    permission_element[:] = []
    for role in roles:
        role_element = ET.SubElement(permission_element, tag='role')
        role_element.text = role
