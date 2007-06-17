# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Library General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
#
# by Aurelien Bompard <abompard@fedoraproject.org>
#

# TODO: for "i" or "n" actions, check that the files are still there (they
#       could have been removed during a "z" action).


import os, sys, md5
from rpm import RPMFILE_CONFIG, RPMFILE_NOREPLACE
from yum.plugins import TYPE_INTERACTIVE

requires_api_version = '2.5'
plugin_type = (TYPE_INTERACTIVE,)


def config_hook(conduit):
    parser = conduit.getOptParser()
    if parser:
        parser.add_option('--merge-conf', action='store_true', 
                      help='Merge configuration changes after installation')

def posttrans_hook(conduit):
    has_vimdiff = False
    for d in os.getenv("PATH", "").split(":"):
        if os.path.exists(os.path.join(d, "vimdiff")):
            has_vimdiff = True
            break
    ts = conduit.getTsInfo()
    for tsmem in ts.getMembers():
        rpmdb = conduit.getRpmDB()
        version = conduit.getYumVersion().replace(".", "")
        if int(version) >= 310:
            packages = rpmdb.searchNevra(tsmem.po.name, tsmem.po.epoch, tsmem.po.version, tsmem.po.release, tsmem.po.arch)
        else:
            # Somehow rpmdb.searchNevra() does not give any result on yum <= 3.0.3
            all_packages = rpmdb.returnPackages()
            packages = []
            for p in all_packages:
                if p.name == tsmem.po.name and p.epoch == tsmem.po.epoch and p.version == tsmem.po.version and p.release == tsmem.po.release and p.arch == tsmem.po.arch:
                    packages.append(p)
                    break
        for package in packages:
            hdr = package.returnLocalHeader()
            files = hdr["filenames"]
            filemodes = hdr["filemodes"]
            fileflags = hdr["fileflags"]
            filetuple = zip(files, filemodes, fileflags)
            for file, mode, flags in filetuple:
                if flags & RPMFILE_CONFIG:
                    if flags & RPMFILE_NOREPLACE:
                        mergeConfFiles(tsmem.po.name, file, True, conduit, has_vimdiff)
                    else:
                        mergeConfFiles(tsmem.po.name, file, False, conduit, has_vimdiff)

def mergeConfFiles(pkg, file, noreplace, conduit, has_vimdiff):
    if noreplace:
        local_file = file
        pkg_file = "%s.rpmnew" % file
        final_file = local_file
        other_file = pkg_file
        if not os.path.exists(pkg_file):
            return
        if md5.new(open(local_file, "r").read()).hexdigest() == md5.new(open(pkg_file, "r").read()).hexdigest():
            conduit.info(2, "Config files '%s' and '%s' are identical, I'm removing the duplicate one" % (local_file, pkg_file))
            os.remove(pkg_file)
            return
    else:
        local_file = "%s.rpmsave" % file
        pkg_file = file
        final_file = pkg_file
        other_file = local_file
        if not os.path.exists(local_file):
            return
        if md5.new(open(local_file, "r").read()).hexdigest() == md5.new(open(pkg_file, "r").read()).hexdigest():
            conduit.info(2, "Config files '%s' and '%s' are identical, I'm removing the duplicate one" % (local_file, pkg_file))
            os.remove(local_file)
            return
    print """\nPackage %s: merging configuration for file "%s":""" % (pkg, final_file)
    answer = ""
    while answer != "q":
        if noreplace:
            print "By default, RPM would keep your local version and rename the new one to %s" % pkg_file
        else:
            print "By default, RPM would rename your local version to %s and put the package's version in place" % local_file
        print "What do you want to do ?"
        print " - diff the two versions (d)"
        print " - do the default RPM action (q)"
        if noreplace:
            print " - install the package's version (i)"
        else:
            print " - keep your version (n)"
        if has_vimdiff:
            print " - merge interactively with vim (v)"
        print " - background this process and examine manually (z)"
        sys.stdout.write("Your answer ? ")
        answer = sys.stdin.readline().strip()

        if answer == "d":
            os.system("""(echo -e "---: local file\n+++: package's file\n"; diff -u '%s' '%s') | less""" % (local_file, pkg_file))
        elif answer == "i":
            print "Installing the package's version..."
            if noreplace: # only useful if noreplace
                os.rename(local_file, local_file+".rpmsave")
                os.rename(pkg_file, final_file)
                print "Your local version has been renamed to %s.rpmsave" % local_file
            break
        elif answer == "n":
            print "Keeping your version..."
            if not noreplace: # Only useful if not noreplace
                os.rename(pkg_file, pkg_file+".rpmnew")
                os.rename(local_file, final_file)
                print "The package's version has been renamed to %s.rpmnew" % pkg_file
            break
        elif answer == "z":
            print "Type 'exit' when you're done"
            os.system(os.getenv("SHELL", "bash"))
        elif answer == "q":
            print "Choosing RPM's default action."
        elif answer == "v" and has_vimdiff:
            os.system("""vimdiff '%s' '%s'""" % (final_file, other_file))
            break
        else:
            print "Unknown answer, please try again"


