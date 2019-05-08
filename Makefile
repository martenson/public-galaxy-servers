
servers.csv:
	echo 'name,url,location' > servers.csv
	curl https://galaxyproject.org/use/feed.json | \
		jq -r '.[] | select(.platforms[].platform_group == "public-server") | [.title, .url, .platforms[].platform_location | select(. != null)] | @csv' | \
		sed 's/"//g' | \
		sort >> servers.csv
