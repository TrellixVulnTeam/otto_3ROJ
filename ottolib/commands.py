"""
Commands class - part of the project otto
"""

# Copyright (C) 2013 Canonical
#
# Authors: Jean-Baptiste Lallement <jean-baptiste.lallement@canonical.com>
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; version 3.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA
#
import argparse
import logging
import subprocess
from textwrap import dedent
from ottolib import utils, container, const


class Commands(object):
    """ Available commands for otto

    This class parses the command line, does some basic checks and sets the
    method for the command passed on the command line
    """
    def __init__(self):
        """ Constructor """
        self.args = None
        self.run = None
        self.container = None
        self.__parse_args()

    def __parse_args(self):
        """ Parse command line arguments """
        parser = argparse.ArgumentParser(
            formatter_class=argparse.RawDescriptionHelpFormatter,
            description=dedent('''\
                Manages containers to run automated UI tests with LXC.

                This script must be run with root privileges without any user logged into a
                graphical session as the display manager will be shutdown.
                Physical devices (video, sound and input) are shared between the host and the
                guest, and any action on one side will have effects on the other side, so it is
                recommended to not touch the device under test while the test is running.
                               '''))
        parser.add_argument('-d', '--debug', action='store_true',
                            default=False, help='enable debug mode')
        subparser = parser.add_subparsers()

        pcreate = subparser.add_parser("create", help="Create a new container")
        pcreate.add_argument("name", help="name of the container")
        pcreate.set_defaults(func=self.cmd_create)

        pdestroy = subparser.add_parser("destroy", help="Destroy a container")
        pdestroy.add_argument("name", help="name of the container")
        pdestroy.set_defaults(func=self.cmd_destroy)

        pstart = subparser.add_parser("start", help="Start a container")
        pstart.add_argument("name", help="name of the container")
        pstart.add_argument("-i", "--image",
                            default=None,
                            help="iso or squashfs to use as rootfs. If an "
                            "ISO is used, the squashfs contained in this "
                            "image will be extracted and used as rootfs")
        pstart.add_argument('-D', '--force-disconnect', action='store_true',
                            default=False,
                            help="Forcibly shutdown lightdm even if a session "
                            "is running and a user might be connected.")
        pstart.set_defaults(func=self.cmd_start)

        pstop = subparser.add_parser("stop", help="Stop a container")
        pstop.add_argument("name", help="name of the container")
        pstop.set_defaults(func=self.cmd_stop)

        self.args = parser.parse_args()
        utils.set_logging(self.args.debug)
        if hasattr(self.args, "func"):
            self.run = self.args.func
            self.container = container.Container(self.args.name)
        else:
            parser.print_help()

    def cmd_create(self):
        """ Creates a new container """
        return self.container.create()

    def cmd_destroy(self):
        """ Destroys a container """
        return self.container.destroy()

    def cmd_start(self):
        """ Starts a container

        @return: Return code of Container.start() method
        """
        # Don't shoot any logged in user
        if not self.args.force_disconnect:
            try:
                subprocess.check_call(["pidof", "gnome-session"])
                logging.warning("gnome-session is running. This likely means "
                                "that a user is logged in and will be "
                                "forcibly disconnected. Please logout before "
                                "starting the container or use option -D")
                return 1
            except subprocess.CalledProcessError:
                pass

        srv = "lightdm"
        ret = utils.service_stop(srv)
        if ret > 2:  # Not enough privileges or Unknown error: Abort
            logging.error("An error occurred while stopping service '%s'. "
                          "Aborting!", srv)
            return ret
        else:
            # An image has been passed on the cmdline, dump the squashfs to
            # cache directory
            if self.args.image is not None:
                self.container.squashfs_path = utils.copy_image(
                    self.args.image, const.CACHEDIR)
                if self.container.squashfs_path is None:
                    return 1

        if not self.container.start():
            return 1

        # Block until the end of the container
        #
        # NOTE:
        # This doesn't support reboots of the container yet. To support
        # reboots we'd need to check that the container is still stopped a
        # little while after the initial 'STOPPED' state. If it is back to
        # 'RUNNING' it'd mean the container restarted, then it should block on
        # 'STOPPED' again with a new timeout = TEST_TIMEOUT -
        # time_elapsed_since_start_of_the_session
        self.container.wait('STOPPED', const.TEST_TIMEOUT)
        if self.container.running:
            logging.error("Test didn't stop within %d seconds",
                          const.TEST_TIMEOUT)
            self.container.stop()  # Or kill
            return 1
        return 0

    def cmd_stop(self):
        """ Stops a container """
        logging.info("Stopping container '%s'", self.args.name)
        logging.info("Container '%s' stopped", self.args.name)
        # TODO:
        #   - Wait for stop
        return self.container.stop()
