Summary: Utilities based around the yum package manager
Name: yum-utils
Version: 0.2
Release: 2
License: GPL
Group: Development/Tools
Source: http://linux.duke.edu/yum/download/yum-utils/%{name}-%{version}.tar.gz
URL: http://linux.duke.edu/yum/download/yum-utils/
BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)
BuildArch: noarch
Requires: python, yum >= 2.3.2

%description
yum-utils is a collection of utilities and examples for the yum package
manager. It includes utilities by different authors that make yum easier and 
more powerful to use.

%package -n yum-updateonboot
Summary: Run yum update on system boot
Group: System Environment/Base
Requires: python, yum >= 2.3.2
Requires(pre): chkconfig
Requires(post): chkconfig

%description -n yum-updateonboot
Runs yum update on system boot. This allows machines that have been turned
off for an extended amount of time to become secure immediately, instead of
waiting until the next early morning cron job.

%prep
%setup -q

%install
rm -rf $RPM_BUILD_ROOT
make DESTDIR=$RPM_BUILD_ROOT install
make -C updateonboot DESTDIR=$RPM_BUILD_ROOT install

%clean
rm -rf $RPM_BUILD_ROOT

%post -n yum-updateonboot
/sbin/chkconfig --add yum-updateonboot >/dev/null 2>&1 || :;

%preun -n yum-updateonboot
if [ $1 = 0 ]; then
    /sbin/service yum-updateonboot stop >/dev/null 2>&1 || :;
    /sbin/chkconfig --del yum >/dev/null 2>&1 || :;
fi

%files
%defattr(-, root, root)
%doc README 
%doc COPYING
%{_bindir}/package-cleanup
%{_bindir}/repoclosure
%{_bindir}/repomanage
%{_bindir}/repoquery
%{_bindir}/repo-rss
%{_bindir}/yumdownloader
%{_bindir}/yum-builddep

%files -n yum-updateonboot
%defattr(-, root, root)
%doc updateonboot/README
%{_sysconfdir}/sysconfig/yum-updateonboot
%{_initrddir}/yum-updateonboot

%changelog
* Tue Jun  21 2005 Gijs Hollestelle <gijs@gewis.nl>
- Added missing GPL COPYING file

* Wed Jun  1 2005 Seth Vidal <skvidal@phy.duke.edu>
- 0.2

* Mon May 23 2005 Panu Matilainen <pmatilai@laiskiainen.org>
- add yum-updateboot subpackage

* Mon May 16 2005 Gijs Hollestelle <gijs@gewis.nl>
- first version based on the mock spec file
