Summary: Utilities based around the yum package manager
Name: yum-utils
Version: 0.1
Release: 1
License: GPL
Group: Development/Tools
Source: %{name}-%{version}.tar.gz
BuildRoot: %{_tmppath}/%{name}-%{version}root
BuildArch: noarch
Requires: python, yum >= 2.3.2

%description
yum-utils is a collection of utilities and examples for the yum package
manager. It includes utilities by different authors that make yum easier and 
more powerful to use.

%prep
%setup -q

%install
[ "$RPM_BUILD_ROOT" != "/" ] && rm -rf $RPM_BUILD_ROOT
make DESTDIR=$RPM_BUILD_ROOT install

%clean
[ "$RPM_BUILD_ROOT" != "/" ] && rm -rf $RPM_BUILD_ROOT

%files
%defattr(-, root, root)
%doc README 
%doc updateonboot 
%{_bindir}/package-cleanup
%{_bindir}/repoclosure
%{_bindir}/repomanage
%{_bindir}/repoquery
%{_bindir}/repo-rss
%{_bindir}/yumdownloader


%changelog
* Mon May 16 2005 Gijs Hollestelle <gijs@gewis.nl>
- first version based on the mock spec file
