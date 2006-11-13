Summary: Utilities based around the yum package manager
Name: yum-utils
Version: 1.0.1
Release: 1
License: GPL
Group: Development/Tools
Source: http://linux.duke.edu/yum/download/yum-utils/%{name}-%{version}.tar.gz
URL: http://linux.duke.edu/yum/download/yum-utils/
BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)
BuildArch: noarch
Requires: python >= 2.4 , yum >= 3.0

%description
yum-utils is a collection of utilities and examples for the yum package
manager. It includes utilities by different authors that make yum easier and 
more powerful to use.

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
Plugin for Yum to handle installation of kmod-foo type of kernel modules, when new kernel versions 
are installed.
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
This plugin allows certain packages specified in a file to be protected from being updated by 
newer versions.

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
This plugin adds a --ignore-broken to yum to make it possible to
check packages for dependency problems and skip the one with problems.

%package -n yum-priorities
Summary: plugin to give priorities to packages from different repos 
Group: System Environment/Base
Requires: yum >= 3.0

%description -n yum-priorities
This plugin allows repositories to have different priorities. 
Packages in a repository with a lower priority can't be overridden by packages
from a repository with a higher priority even if repo has a later version.

%prep
%setup -q

%install
rm -rf $RPM_BUILD_ROOT
make DESTDIR=$RPM_BUILD_ROOT install
make -C updateonboot DESTDIR=$RPM_BUILD_ROOT install

# Plugins to install
plugins="changelog fastestmirror fedorakmod protectbase versionlock tsflags kernel-module downloadonly allowdowngrade skip-broken priorities"
mkdir -p $RPM_BUILD_ROOT/%{_sysconfdir}/yum/pluginconf.d/ $RPM_BUILD_ROOT/usr/lib/yum-plugins/

cd plugins
for plug in $plugins; do
    install -m 644 $plug/*.conf $RPM_BUILD_ROOT/%{_sysconfdir}/yum/pluginconf.d/
    install -m 644 $plug/*.py $RPM_BUILD_ROOT/usr/lib/yum-plugins/
done

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
%doc README 
%doc COPYING
%doc plugins/README
%{_bindir}/package-cleanup
%{_bindir}/repoclosure
%{_bindir}/repomanage
%{_bindir}/repoquery
%{_bindir}/repotrack
%{_bindir}/reposync
%{_bindir}/repo-graph
%{_bindir}/repo-rss
%{_bindir}/yumdownloader
%{_bindir}/yum-builddep
%{_mandir}/man1/*

%files -n yum-updateonboot
%defattr(-, root, root)
%doc updateonboot/README
%config(noreplace) %{_sysconfdir}/sysconfig/yum-updateonboot
%{_initrddir}/yum-updateonboot

%files -n yum-changelog
%defattr(-, root, root)
%config(noreplace) %{_sysconfdir}/yum/pluginconf.d/changelog.conf
/usr/lib/yum-plugins/changelog.*

%files -n yum-fastestmirror
%defattr(-, root, root)
%config(noreplace) %{_sysconfdir}/yum/pluginconf.d/fastestmirror.conf
/usr/lib/yum-plugins/fastestmirror.*

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
%config(noreplace) %{_sysconfdir}/yum/pluginconf.d/versionlock.conf
/usr/lib/yum-plugins/versionlock.*

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

%files -n yum-skip-broken
%defattr(-, root, root)
%config(noreplace) %{_sysconfdir}/yum/pluginconf.d/skip-broken.conf
/usr/lib/yum-plugins/skip-broken.*

%files -n yum-priorities
%defattr(-, root, root)
%config(noreplace) %{_sysconfdir}/yum/pluginconf.d/priorities.conf
/usr/lib/yum-plugins/priorities.*


%changelog
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
