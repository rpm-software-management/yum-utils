Summary: Utilities based around the yum package manager
Name: yum-utils
Version: 1.1.17
Release: 1%{?dist}
License: GPLv2+
Group: Development/Tools
Source: http://linux.duke.edu/yum/download/yum-utils/%{name}-%{version}.tar.gz
URL: http://linux.duke.edu/yum/download/yum-utils/
BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)
BuildArch: noarch
Requires: python >= 2.4 , yum >= 3.2.20

%description
yum-utils is a collection of utilities and examples for the yum package
manager. It includes utilities by different authors that make yum easier and
more powerful to use. These tools include: debuginfo-install, package-cleanup,
repoclosure, repodiff, repo-graph, repomanage, repoquery, repo-rss, reposync,
repotrack, verifytree, yum-builddep, yum-complete-transaction, yumdownloader,
yum-debug-dump and yum-groups-manager.

%package -n yum-updateonboot
Summary: Run yum update on system boot
Group: System Environment/Base
Requires: python, yum >= 2.4
Requires(pre): chkconfig
Requires(post): chkconfig

%description -n yum-updateonboot
Runs yum update on system boot. This allows machines that have been turned
off for an extended amount of time to become secure immediately, instead of
waiting until the next early morning cron job.

%package -n yum-changelog
Summary: Yum plugin for viewing package changelogs before/after updating
Group: System Environment/Base
Requires: yum >= 3.0
Requires: python-dateutil

%description -n yum-changelog
This plugin adds a command line option to allow viewing package changelog
deltas before or after updating packages.

%package -n yum-fastestmirror
Summary: Yum plugin which chooses fastest repository from a mirrorlist
Group: System Environment/Base
Requires: yum >= 3.0

%description -n yum-fastestmirror
This plugin sorts each repository's mirrorlist by connection speed
prior to downloading packages.

%package -n yum-fedorakmod
Summary: Yum plugin to handle fedora kernel modules.
Group: System Environment/Base
Requires: yum >= 3.0

%description -n yum-fedorakmod
Plugin for Yum to handle installation of kmod-foo type of kernel modules,
when new kernel versions are installed.
kmod-foo kernel modules is described by the Fedora Extras packaging standards.

%package -n yum-protectbase
Summary: Yum plugin to protect packages from certain repositories.
Group: System Environment/Base
Requires: yum >= 3.0

%description -n yum-protectbase
This plugin allows certain repositories to be protected. Packages in the
protected repositories can't be overridden by packages in non-protected
repositories even if the non-protected repo has a later version.

%package -n yum-versionlock
Summary: Yum plugin to lock specified packages from being updated
Group: System Environment/Base
Requires: yum >= 3.0

%description -n yum-versionlock
This plugin takes a set of name/versions for packages and excludes all other
versions of those packages (including optionally following obsoletes). This
allows you to protect packages from being updated by newer versions,
for example.

%package -n yum-tsflags
Summary: Yum plugin to add tsflags by a commandline option
Group: System Environment/Base
Requires: yum >= 3.0

%description -n yum-tsflags
This plugin allows you to specify optional transaction flags on the yum
command line

%package -n yum-kernel-module
Summary: Yum plugin to handle kernel-module-foo type of kernel module
Group: System Environment/Base
Requires: yum >= 3.0

%description -n yum-kernel-module
This plugin handle installation of kernel-module-foo type of kernel modules when new version of
kernels are installed.


%package -n yum-downloadonly
Summary: Yum plugin to add downloadonly command option
Group: System Environment/Base
Requires: yum >= 3.0

%description -n yum-downloadonly
This plugin adds a --downloadonly flag to yum so that yum will only download
the packages and not install/update them.

%package -n yum-allowdowngrade
Summary: Yum plugin to enable manual downgrading of packages
Group: System Environment/Base
Requires: yum >= 3.0

%description -n yum-allowdowngrade
This plugin adds a --allow-downgrade flag to yum to make it possible to
manually downgrade packages to specific versions.

%package -n yum-skip-broken
Summary: Yum plugin to handle skiping packages with dependency problems
Group: System Environment/Base
Requires: yum >= 3.0

%description -n yum-skip-broken
This plugin adds a --skip-broken to yum to make it possible to
check packages for dependency problems and skip the one with problems.

%package -n yum-priorities
Summary: plugin to give priorities to packages from different repos
Group: System Environment/Base
Requires: yum >= 3.0

%description -n yum-priorities
This plugin allows repositories to have different priorities.
Packages in a repository with a lower priority can't be overridden by packages
from a repository with a higher priority even if repo has a later version.

%package -n yum-refresh-updatesd
Summary: Tell yum-updatesd to check for updates when yum exits
Group: System Environment/Base
Requires: yum >= 3.0
Requires: yum-updatesd

%description -n yum-refresh-updatesd
yum-refresh-updatesd tells yum-updatesd to check for updates when yum exits.
This way, if you run 'yum update' and install all available updates, puplet
will almost instantly update itself to reflect this.

%package -n yum-merge-conf
Summary: Yum plugin to merge configuration changes when installing packages
Group: System Environment/Base
Requires: yum >= 3.0

%description -n yum-merge-conf
This yum plugin adds the "--merge-conf" command line option. With this option,
Yum will ask you what to do with config files which have changed on updating a
package.

%package -n yum-security
Summary: Yum plugin to enable security filters
Group: System Environment/Base
Requires: yum >= 3.2.18

%description -n yum-security
This plugin adds the options --security, --cve, --bz and --advisory flags
to yum and the list-security and info-security commands.
The options make it possible to limit list/upgrade of packages to specific
security relevant ones. The commands give you the security information.

%package -n yum-protect-packages
Summary: Yum plugin to prevents Yum from removing itself and other protected packages
Group: System Environment/Base
Requires: yum >= 3.0

%description -n yum-protect-packages
this plugin prevents Yum from removing itself and other protected packages.
By default, yum is the only package protected, but by extension this
automatically protects everything on which yum depends (rpm, python, glibc,
and so on).Therefore, the plugin functions well even without
compiling careful lists of all important packages.

%package -n yum-basearchonly
Summary: Yum plugin to let Yum install only basearch packages.
Group: System Environment/Base
Requires: yum >= 3.0

%description -n yum-basearchonly
this plugin makes Yum only install basearch packages on multiarch systems.
If you type 'yum install foo' on a x68_64 system, only 'foo-x.y.x86_46.rpm' is installed.
If you want to install the foo-x.y.i386.rpm, you have to type 'yum install foo.i386'.
The plugin only works with 'yum install'.

%package -n yum-upgrade-helper
Summary: Yum plugin to help upgrades to the next distribution version
Group: System Environment/Base
Requires: yum >= 3.0

%description -n yum-upgrade-helper
this plugin allows yum to erase specific packages on install/update based on an additional
metadata file in repositories. It is used to simplify distribution upgrade hangups.

%package -n yum-aliases
Summary: Yum plugin to enable aliases filters
Group: System Environment/Base
Requires: yum >= 3.0.5

%description -n yum-aliases
This plugin adds the command alias, and parses the aliases config. file to
enable aliases.

%package -n yum-list-data
Summary: Yum plugin to list aggregate package data
Group: System Environment/Base
Requires: yum >= 3.0.5

%description -n yum-list-data
This plugin adds the commands list- vendors, groups, packagers, licenses,
arches, committers, buildhosts, baseurls, package-sizes, archive-sizes and
installed-sizes.

%package -n yum-filter-data
Summary: Yum plugin to list filter based on package data
Group: System Environment/Base
Requires: yum >= 3.2.17

%description -n yum-filter-data
This plugin adds the options --filter- vendors, groups, packagers, licenses,
arches, committers, buildhosts, baseurls, package-sizes, archive-sizes and
installed-sizes. Note that each package must match at least one pattern/range in
each category, if any were specified.

%package -n yum-tmprepo
Summary: Yum plugin to add temporary repositories
Group: System Environment/Base
Requires: yum >= 3.2.11
Requires: createrepo

%description -n yum-tmprepo
This plugin adds the option --tmprepo which takes a url to a .repo file
downloads it and enables it for a single run. This plugin tries to ensure
that temporary repositories are safe to use, by default, by not allowing
gpg checking to be disabled.

%package -n yum-verify
Summary: Yum plugin to add verify command, and options
Group: System Environment/Base
Requires: yum >= 3.2.12

%description -n yum-verify
This plugin adds the commands verify, verify-all and verify-rpm. There are
also a couple of options. This command works like rpm -V, to verify your
installation.

%package -n yum-keys
Summary: Yum plugin to deal with signing keys
Group: System Environment/Base
Requires: yum >= 3.2.19

%description -n yum-keys
This plugin adds the commands keys, keys-info, keys-data and keys-remove. They
allow you to query and remove signing keys.

%package -n yum-remove-with-leaves
Summary: Yum plugin to remove dependencies which are no longer used because of a removal
Group: System Environment/Base
Requires: yum >= 3.2.19

%description -n yum-remove-with-leaves
This plugin removes any unused dependencies that were brought in by an install
but would not normally be removed. It helps to keep a system clean of unused
libraries and packages.

%package -n yum-NetworkManager-dispatcher
Summary: Yum plugin to deal with changing networks with NetworkManager
Group: System Environment/Base
Requires: yum >= 3.2.17

%description -n yum-NetworkManager-dispatcher
This plugin forces yum to check it's cache if/when a new network connection
happens in NetworkManager. Note that currently there is no checking of
previous data, so if your WiFi keeps going up and down (or you suspend/resume
a lot) yum will recheck it's cached data a lot.

%prep
%setup -q

%install
rm -rf $RPM_BUILD_ROOT
make DESTDIR=$RPM_BUILD_ROOT install
make -C updateonboot DESTDIR=$RPM_BUILD_ROOT install

# Plugins to install
plugins="\
 changelog \
 fastestmirror \
 fedorakmod \
 protectbase \
 versionlock \
 tsflags \
 kernel-module \
 downloadonly \
 allowdowngrade \
 priorities \
 refresh-updatesd \
 merge-conf \
 security \
 protect-packages \
 basearchonly \
 upgrade-helper \
 aliases \
 list-data \
 filter-data \
 tmprepo \
 verify \
 keys \
 remove-with-leaves \
"

mkdir -p $RPM_BUILD_ROOT/%{_sysconfdir}/yum/pluginconf.d/ $RPM_BUILD_ROOT/usr/lib/yum-plugins/

cd plugins
for plug in $plugins; do
    install -m 644 $plug/*.conf $RPM_BUILD_ROOT/%{_sysconfdir}/yum/pluginconf.d/
    install -m 644 $plug/*.py $RPM_BUILD_ROOT/usr/lib/yum-plugins/
done
install -m 644 aliases/aliases $RPM_BUILD_ROOT/%{_sysconfdir}/yum/aliases.conf
install -m 644 versionlock/versionlock.list $RPM_BUILD_ROOT/%{_sysconfdir}/yum/pluginconf.d/

%clean
rm -rf $RPM_BUILD_ROOT

%post -n yum-updateonboot
/sbin/chkconfig --add yum-updateonboot >/dev/null 2>&1 || :;

%preun -n yum-updateonboot
if [ $1 = 0 ]; then
    /sbin/service yum-updateonboot stop >/dev/null 2>&1 || :;
    /sbin/chkconfig --del yum-updateonboot >/dev/null 2>&1 || :;
fi

%files
%defattr(-, root, root)
%doc README yum-util-cli-template
%doc COPYING
%doc plugins/README
%{_bindir}/debuginfo-install
%{_bindir}/package-cleanup
%{_bindir}/repoclosure
%{_bindir}/repodiff
%{_bindir}/repomanage
%{_bindir}/repoquery
%{_bindir}/repotrack
%{_bindir}/reposync
%{_bindir}/repo-graph
%{_bindir}/repo-rss
%{_bindir}/verifytree
%{_bindir}/yumdownloader
%{_bindir}/yum-builddep
%{_bindir}/yum-debug-dump
%{_bindir}/yum-groups-manager
%{_sbindir}/yum-complete-transaction
%{_mandir}/man1/yum-utils.1.*
%{_mandir}/man1/debuginfo-install.1.*
%{_mandir}/man1/package-cleanup.1.*
%{_mandir}/man1/repo-rss.1.*
%{_mandir}/man1/repoquery.1.*
%{_mandir}/man1/reposync.1.*
%{_mandir}/man1/yum-builddep.1.*
%{_mandir}/man1/yum-debug-dump.1.*
%{_mandir}/man8/yum-complete-transaction.8.*
%{_mandir}/man1/yum-groups-manager.1.*
%{_mandir}/man1/yumdownloader.1.*

%files -n yum-updateonboot
%defattr(-, root, root)
%doc updateonboot/README
%config(noreplace) %{_sysconfdir}/sysconfig/yum-updateonboot
%{_initrddir}/yum-updateonboot

%files -n yum-changelog
%defattr(-, root, root)
%config(noreplace) %{_sysconfdir}/yum/pluginconf.d/changelog.conf
/usr/lib/yum-plugins/changelog.*
%{_mandir}/man1/yum-changelog.1.*
%{_mandir}/man5/yum-changelog.conf.5.*

%files -n yum-fastestmirror
%defattr(-, root, root)
%config(noreplace) %{_sysconfdir}/yum/pluginconf.d/fastestmirror.conf
/usr/lib/yum-plugins/fastestmirror*.*

%files -n yum-fedorakmod
%defattr(-, root, root)
%config(noreplace) %{_sysconfdir}/yum/pluginconf.d/fedorakmod.conf
/usr/lib/yum-plugins/fedorakmod.*

%files -n yum-protectbase
%defattr(-, root, root)
%config(noreplace) %{_sysconfdir}/yum/pluginconf.d/protectbase.conf
/usr/lib/yum-plugins/protectbase.*

%files -n yum-versionlock
%defattr(-, root, root)
%doc plugins/versionlock/README
%config(noreplace) %{_sysconfdir}/yum/pluginconf.d/versionlock.conf
%config(noreplace) %{_sysconfdir}/yum/pluginconf.d/versionlock.list
/usr/lib/yum-plugins/versionlock.*
%{_mandir}/man1/yum-versionlock.1.*
%{_mandir}/man5/yum-versionlock.conf.5.*

%files -n yum-tsflags
%defattr(-, root, root)
%config(noreplace) %{_sysconfdir}/yum/pluginconf.d/tsflags.conf
/usr/lib/yum-plugins/tsflags.*

%files -n yum-kernel-module
%defattr(-, root, root)
%config(noreplace) %{_sysconfdir}/yum/pluginconf.d/kernel-module.conf
/usr/lib/yum-plugins/kernel-module.*

%files -n yum-downloadonly
%defattr(-, root, root)
%config(noreplace) %{_sysconfdir}/yum/pluginconf.d/downloadonly.conf
/usr/lib/yum-plugins/downloadonly.*

%files -n yum-allowdowngrade
%defattr(-, root, root)
%config(noreplace) %{_sysconfdir}/yum/pluginconf.d/allowdowngrade.conf
/usr/lib/yum-plugins/allowdowngrade.*

%files -n yum-priorities
%defattr(-, root, root)
%config(noreplace) %{_sysconfdir}/yum/pluginconf.d/priorities.conf
/usr/lib/yum-plugins/priorities.*

%files -n yum-refresh-updatesd
%defattr(-, root, root)
%config(noreplace) %{_sysconfdir}/yum/pluginconf.d/refresh-updatesd.conf
/usr/lib/yum-plugins/refresh-updatesd.*

%files -n yum-merge-conf
%defattr(-, root, root)
%config(noreplace) %{_sysconfdir}/yum/pluginconf.d/merge-conf.conf
/usr/lib/yum-plugins/merge-conf.*

%files -n yum-security
%defattr(-, root, root)
%config(noreplace) %{_sysconfdir}/yum/pluginconf.d/security.conf
/usr/lib/yum-plugins/security.*
%{_mandir}/man8/yum-security.8.*

%files -n yum-protect-packages
%defattr(-, root, root)
%config(noreplace) %{_sysconfdir}/yum/pluginconf.d/protect-packages.conf
/usr/lib/yum-plugins/protect-packages.*

%files -n yum-basearchonly
%defattr(-, root, root)
%config(noreplace) %{_sysconfdir}/yum/pluginconf.d/basearchonly.conf
/usr/lib/yum-plugins/basearchonly.*

%files -n yum-upgrade-helper
%defattr(-, root, root)
%config(noreplace) %{_sysconfdir}/yum/pluginconf.d/upgrade-helper.conf
/usr/lib/yum-plugins/upgrade-helper.*

%files -n yum-aliases
%defattr(-, root, root)
%config(noreplace) %{_sysconfdir}/yum/pluginconf.d/aliases.conf
%config(noreplace) %{_sysconfdir}/yum/aliases.conf
/usr/lib/yum-plugins/aliases.*
%{_mandir}/man1/yum-aliases.1.*

%files -n yum-list-data
%defattr(-, root, root)
%config(noreplace) %{_sysconfdir}/yum/pluginconf.d/list-data.conf
/usr/lib/yum-plugins/list-data.*
%{_mandir}/man1/yum-list-data.1.*

%files -n yum-filter-data
%defattr(-, root, root)
%config(noreplace) %{_sysconfdir}/yum/pluginconf.d/filter-data.conf
/usr/lib/yum-plugins/filter-data.*
%{_mandir}/man1/yum-filter-data.1.*

%files -n yum-tmprepo
%defattr(-, root, root)
%config(noreplace) %{_sysconfdir}/yum/pluginconf.d/tmprepo.conf
/usr/lib/yum-plugins/tmprepo.*

%files -n yum-verify
%defattr(-, root, root)
%config(noreplace) %{_sysconfdir}/yum/pluginconf.d/verify.conf
/usr/lib/yum-plugins/verify.*
%{_mandir}/man1/yum-verify.1.*

%files -n yum-keys
%defattr(-, root, root)
%config(noreplace) %{_sysconfdir}/yum/pluginconf.d/keys.conf
/usr/lib/yum-plugins/keys.*

%files -n yum-NetworkManager-dispatcher
%defattr(-, root, root)
/etc/NetworkManager/dispatcher.d/*

%files -n yum-remove-with-leaves
%defattr(-, root, root)
/usr/lib/yum-plugins/remove-with-leaves.*
%config(noreplace) %{_sysconfdir}/yum/pluginconf.d/remove-with-leaves.conf

%changelog
* Fri Sep 19 2008 Tim Lauridsen <timlau@fedoraproject.org>
- removed skip-broken plugin

* Wed Sep 17 2008 Tim Lauridsen <timlau@fedoraproject.org>
- mark as 1.1.17

* Mon Sep  8 2008 Seth Vidal <skvidal at fedoraproject.org>
- add yum-remove-with-leaves plugin

* Wed Aug 27 2008 Tim Lauridsen <timlau@fedoraproject.org>
- mark as 1.1.16
* Wed Aug 20 2008 James Antill <james@fedoraproject.org>
- add yum-groups-manager

* Thu Aug 7 2008 Tim Lauridsen <timlau@fedoraproject.org>
- mark as 1.1.15
* Wed May 21 2008 Tim Lauridsen <timlau@fedoraproject.org>
- add verifytree

* Wed May 21 2008 Tim Lauridsen <timlau@fedoraproject.org>
  Make yum-fastestmirror %%files handle the fastestmirror-asyncore.py file
* Wed May 21 2008 Tim Lauridsen <timlau@fedoraproject.org>
- mark as 1.1.14
* Fri Apr 10 2008 James Antill <james@fedoraproject.org>
- Add keys plugin

* Fri Mar 31 2008 James Antill <james@fedoraproject.org>
- Add yum-aliases man page

* Fri Mar 21 2008 Tim Lauridsen <timlau@fedoraproject.org>
- mark as 1.1.13
* Fri Mar 21 2008 Tim Lauridsen <timlau@fedoraproject.org>
- mark as 1.1.12
* Tue Mar 18 2008 Shawn Starr <shawn.starr@rogers.com>
- Add yum-utils.1 manual page
- Rename yum-complete-transaction manual page to 8
- Move yum-complete-transaction to /usr/sbin

* Sat Mar  1 2008 James Antill <james@fedoraproject.org>
- Add verify plugin

* Wed Feb 20 2008 James Antill <james@fedoraproject.org>
- Add empty versionlock file

* Fri Feb  1 2008 James Antill <james@fedoraproject.org>
- Add filter-data plugin

* Wed Jan 30 2008 Tim Lauridsen <timlau@fedoraproject.org>
- mark as 1.1.11

* Sun Jan 13 2008 Seth Vidal <skvidal at fedoraproject.org>
- add repodiff

* Thu Jan 3 2008 Tim Lauridsen <timlau@fedoraproject.org>
- mark as 1.1.10

* Thu Dec 12 2007 James Antill <james@fedoraproject.org>
- Add yum-aliases plugin

* Fri Dec 7 2007 Tim Lauridsen <timlau@fedoraproject.org>
- mark as 1.1.9
* Fri Oct 26 2007 Seth Vidal <skvidal at fedoraproject.org>
- add upgrade-helper plugin
* Wed Oct 17 2007 Tim Lauridsen <tla@rasmil.dk>
- mark as 1.1.8
* Sun Sep 30 2007 James Bowes <jbowes@redhat.com>
- Update the yum-refresh-updatesd description

* Mon Sep 14 2007 Tim Lauridsen <tla@rasmil.dk>
- do not use wildcards for manpages in yum-utils files section to avoid duplicates
* Mon Sep 10 2007 Tim Lauridsen <tla@rasmil.dk>
- mark as 1.1.7
* Tue Jul 24 2007 Tim Lauridsen <tla@rasmil.dk>
- Added basearchonly plugin by Adel Gadllah
* Tue Jul 24 2007 Tim Lauridsen <tla@rasmil.dk>
- mark as 1.1.6
* Tue Jul 17 2007 Tim Lauridsen <tla@rasmil.dk>
- Added Requires: yum-updatesd to yum-refresh-updatesd
* Tue Jul 03 2007 Panu Matilainen <pmatilai@laiskiainen.org>
- Add versionlock list format documentation

* Mon Jun 18 2007 Tim Lauridsen <tla@rasmil.dk>
- Added protect-packages plugin by Svetlana Anissimova and Matthew Miller

* Mon Jun 18 2007 Tim Lauridsen <tla@rasmil.dk>
- mark as 1.1.5

* Tue May 1 2007 Tim Lauridsen <tla@rasmil.dk>
- mark as 1.1.4

* Tue May 1 2007 Tim Lauridsen <tla@rasmil.dk>
- mark as 1.1.3

* Tue May  1 2007 Seth Vidal <skvidal at linux.duke.edu>
- added debuginfo-install

* Fri Apr 20 2007 Tim Lauridsen <tla@rasmil.dk>
- Added security plugin written by James Antill <james@and.org>

* Thu Apr 12 2007 Tim Lauridsen <tla@rasmil.dk>
- mark as 1.1.2
- Added merge-conf plugin written by Aurelien Bompard <abompard@fedoraproject.org>

* Mon Feb 19 2007 Tim Lauridsen <tla@rasmil.dk>
- mark it as 1.1.1

* Mon Feb 19 2007 Tim Lauridsen <tla@rasmil.dk>
- mark it as 1.1.0 (again)

* Thu Feb 15 2007 Tim Lauridsen <tla@rasmil.dk>
- removed versionlock.list installation.

* Wed Feb 14 2007 Tim Lauridsen <tla@rasmil.dk>
- Added versionlock.list installation.
- fixed skip-broken description (--ignore-broken -> --skip-broken)

* Tue Feb 13 2007 James Bowes <jbowes@redhat.com>
- Add yum-refresh-updatesd plugin

* Thu Feb 8 2007 Tim Lauridsen <tla@rasmil.dk>
- Added man dirs to yum-changelog files section

* Wed Feb 7 2007 Tim Lauridsen <tla@rasmil.dk>
- mark it as 1.1.0
- Requires: yum >= 3.1.1 for yum-utils.

* Tue Feb 6 2007 Tim Lauridsen <tla@rasmil.dk>
- Added %%{?dist} tag

* Sun Dec 31 2006 Tim Lauridsen <tla@rasmil.dk>
- mark it as 1.0.2

* Tue Oct 31 2006 Tim Lauridsen <tla@rasmil.dk>
- mark it as 1.0.1

* Fri Oct 27 2006 Tim Lauridsen <tla@rasmil.dk>
- Added priorities plugin written by Daniel de Kok <danieldk at pobox.com>

* Wed Oct  4 2006 Seth Vidal <skvidal at linux.duke.edu>
- mark it as 1.0
- change requires for the packages to yum 3.0

* Wed Sep 27 2006 Tim Lauridsen <tla@rasmil.dk>
- added skip-broken plugin

* Tue Sep 05 2006 Panu Matilainen <pmatilai@laiskianen.org>
- added allowdowngrade plugin

* Sun Aug 13 2006 Seth Vidal <skvidal at linux.duke.edu>
- fix the plugins/ doc issue

* Sat May  6 2006 Seth Vidal <skvidal at linux.duke.edu>
- bump version number
- added yum-downloadonly plugin
- fix minor item in tsflags description

* Sat Apr 29 2006 Seth Vidal <skvidal at linux.duke.edu>
- add reposync

* Fri Apr 28 2006 Tim Lauridsen <tla@rasmil.dk>
- added yum-fedorakmod plugin subpackage
- added yum-protectbase plugin subpackage.
- added yum-versionlock plugin subpackage.
- added yum-tsflags plugin subpackage.
- added yum-kernel-module plugin subpackage
- changed .py to .* in files sections for plugin subpackages to build rpms without error.

* Thu Feb 23 2006 Seth Vidal <skvidal at linux.duke.edu>
-  changed some of the yum version dependencies

* Fri Feb 10 2006 Seth Vidal <skvidal@linux.duke.edu>
- added repotrack to utils
- bumped version for 2.5.X-compatible release

* Tue Jan 10 2006 Brian Long <brilong@cisco.com>
- bump version to 0.4
- add yum-fastestmirror subpackage

* Mon Oct 17 2005 Panu Matilainen <pmatilai@laiskiainen.org>
- add repoquery man page

* Sat Sep 17 2005 Panu Matilainen <pmatilai@laiskiainen.org>
- version 0.3.1
- various enhancements and fixes to repoquery
- avoid tracebacks in yumex and pup when changelog plugin is enabled

* Mon Jul 25 2005 Panu Matilainen <pmatilai@laiskiainen.org>
- bump version to 0.3
- add yum-changelog subpackage
- add plugins as documentation to the main package
- require yum >= 2.3.4 (for getCacheDir)

* Tue Jun  21 2005 Gijs Hollestelle <gijs@gewis.nl>
- Added missing GPL COPYING file

* Wed Jun  1 2005 Seth Vidal <skvidal@phy.duke.edu>
- 0.2

* Mon May 23 2005 Panu Matilainen <pmatilai@laiskiainen.org>
- add yum-updateboot subpackage

* Mon May 16 2005 Gijs Hollestelle <gijs@gewis.nl>
- first version based on the mock spec file
