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
    security = configurator._GoCdConfigurator__server_element_ensurance().ensure_child('security')
    roles = security.ensure_child('roles')
    roles.ensure_child_with_attribute('role', 'name', role)


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

    authorization = Ensurance(pipeline_group.element).ensure_child('authorization')
    permission = authorization.ensure_child(permission.value)
    permission.element[:] = []
    for role in roles:
        role_element = ET.SubElement(permission.element, tag='role')
        role_element.text = role
