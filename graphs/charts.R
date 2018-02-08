library(ggplot2)
library(reshape2)

d = read.csv('releases.tsv', sep="\t")
d$X. = as.Date(d$X.)
molten = melt(d, "X.")
g = ggplot(molten, aes(x=X., y=value, fill=variable, width=1)) + geom_bar(stat="identity") + scale_fill_brewer(palette="Paired") + labs(x="Date", y="# of Public Galaxy Servers", title="Galaxy Upgrades over Time", variable="Version")
ggsave("releases.png", plot=g, width=5, height=4)


d = read.csv('releases_supported.tsv', sep="\t")
d$X. = as.Date(d$X.)
molten = melt(d, "X.")
g = ggplot(molten, aes(x=X., y=value, fill=variable, width=1)) + geom_bar(stat="identity") + scale_fill_brewer(palette="Paired") + labs(x="Date", y="# of Public Galaxy Servers", title="Galaxy Upgrades over Time", variable="Version")
ggsave("releases_supported.png", plot=g, width=5, height=4)
