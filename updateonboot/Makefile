install:
	mkdir -p $(DESTDIR)/etc/sysconfig
	mkdir -p $(DESTDIR)/etc/rc.d/init.d
	install -m 644 yum-updateonboot.sysconfig $(DESTDIR)/etc/sysconfig/yum-updateonboot
	install -m 755 yum-updateonboot.init $(DESTDIR)/etc/rc.d/init.d/yum-updateonboot

